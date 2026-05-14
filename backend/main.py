import os
import sys
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database.timescale import get_connection

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)

from config import (
    ALL_COINS, 
    BASE_URL, 
    MARKET_CAP_LOOKUP, 
    REQUEST_TIMEOUT
)
from calculate_rho import (
    calculate_rho,
    get_signal,
    THRESHOLDS,
    KAPPA, IOTA, GAMMA, RISK_FREE_RATE_8HR, PERIODS_PER_YEAR
)
from calculate_funding import annualize_funding_rate, get_funding_signal
from update_data import run_price_update, run_funding_rates_update


# -------------------------------- LOGGING ---------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# -------------------------------- MARKET CAP DATA --------------------------------------
def load_market_cap_data():
    """
    This function loads market cap classification from the database
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol, name, market_cap_rank, market_cap_tier
                    FROM coin_universe
                    WHERE is_active = true
                    ORDER BY market_cap_rank ASC NULLS LAST
                """)
                rows = cur.fetchall()


        MARKET_CAP_LOOKUP.clear()
        ALL_COINS.clear()

        for row in rows:
            MARKET_CAP_LOOKUP[row['symbol']] = {
                'tier': row['market_cap_tier'] or 'Unknown',
                'rank': row['market_cap_rank'] or 9999,
                'name': row['name'] or row['symbol']
            }
            ALL_COINS.append(row['symbol'])

        logger.info(f"Loaded {len(MARKET_CAP_LOOKUP)} coins from database")
        return
    
    except Exception as e:
        logger.warning(f"Database load failed: {e}. Trying JSON fallback..."
                       f"Using config.py data: {len(MARKET_CAP_LOOKUP)} coins loaded.")


# -------------------------------------- APP SETUP ----------------------------------------------
async def lifespan(app: FastAPI):
    # startup
    logger.info("PerpScope API starting up...")
    load_market_cap_data()
    logger.info("Startup complete!")

    yield

    # shutdown
    logger.info("Cleaning up...")


app = FastAPI(
    title="PerpScope API",
    description=(
        "Altcoin perpetual futures analytics API."
        "Implements no-arbitrage pricing from He, Manela, Ross & von Wachter (2024)"
    ),
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware, 
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://perpscope.vercel.app",
        "*" # Remember to replace this with my actual vercel url before going live
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ------------------------------------- DATA ENDPOINTS ------------------------------------------
def get_coin_metadata(symbol):
    """
    This function returns market cap metadata for one coin.
    """
    return MARKET_CAP_LOOKUP.get(symbol, {
        'tier': 'Unknown',
        'rank': 9999,
        'name': symbol.replace('USDT', '')
    })


@app.get("/api/coins")
async def get_all_coins():
    """
    This function returns the full list of monitored coins with metadata.
    """
    coins = []
    
    for symbol in ALL_COINS:
        metadata = get_coin_metadata(symbol)
        coins.append({
            'symbol': symbol,
            'name': metadata['name'],
            'tier': metadata['rank'],
            'market_cap_rank': metadata['rank'],
            'display_symbol': symbol.replace('USDT', '')
        })

    return {
        'total': len(coins),
        'coins': coins
    }


@app.get("/api/opportunities")
async def get_opportunities(
    threshold=Query("high", description="Trading cost tier: no_fee|low|medium|high"),
    tier=Query('all', description="Market cap filter: all|Large Cap|Mid Cap|Small Cap")):
    """
    This is the main endpoint. Powers the opportunity ranker table on the dashboard

    For every coin, this function fetches the latest perp and spot price,
    calculates rho, determines the signal, and returns everything sorted
    with opportunities (i.e |rho| above the threshold) at the top.
    """
    if threshold not in THRESHOLDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid threshold '{threshold}'. Choose from {list(THRESHOLDS.keys())}"
        )
    
    # Fetch latest perp + spot price for every coin
    sql = """
        WITH latest_perp AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS perp_price,
                timestamp   AS last_updates
            FROM perp_prices
            ORDER BY symbol, timestamp_ms DESC
        ),
        latest_spot AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS spot_price,
                timestamp   AS last_updates
            FROM spot_prices
            ORDER BY symbol, timestamp_ms DESC
        )
        SELECT
            p.symbol,
            s.spot_price,
            p.perp_price
            p.last_updated
        FROM latest_perp p
        JOIN latest_spot s ON p.symbol = s.symbol
        ORDER BY p.symbol
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if not rows:
        raise HTTPException(status_code=503, detail="No price data available yet")
    
    
    results = []

    for row in rows:
        symbol     = row['symbol']
        perp_price = float(row['perp_price'])
        spot_price = float(row['spot_price'])
        metadata   = get_coin_metadata(symbol)

        if tier != "all" and metadata['tier'] != tier:
            continue

        rho = calculate_rho(perp_price, spot_price)
        signal = get_signal(rho, threshold)

        results.append({
            "symbol":           symbol,
            "display_symbol":   symbol.replace('USDT', ''),
            "name":             metadata['name'],
            "tier":             metadata['tier'],
            "market_cap_rank":  metadata['rank'],
            "perp_price":       round(perp_price, 8),
            "spot_price":       round(spot_price, 8),
            "premium_pct":      round((perp_price - spot_price) / spot_price * 100, 4),
            "rho":              round(rho, 4),
            "abs_rho":          round(abs(rho), 4),
            "signal":           signal,
            "is_opportunity":   signal != 'NEUTRAL',
            "last_updated":     row['last_updated'].isoformat()
        })

        # Sorting by opportunities first (using the 'not' to make True values come first),
        # then by abs_rho descending within each group
        results.sort(key=lambda x: (not x['is_opportunity'], -x['abs_rho']))

        return {
            "threshold_tier":    threshold,
            "threhold_value":    THRESHOLDS[threshold],
            "total_coins":       len(results),
            "opportunity_count": sum(1 for r in results if r['is_opportunity']),
            "data":              results
        }


@app.get("/api/coin/{symbol}")
async def get_coin_detail(symbol):
    """This function returns the current details for a specific coin"""
    symbol = symbol.upper()

    sql = """
        WITH latest_perp AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close AS perp_price,
                timestamp
            FROM perp_prices
            WHERE symbol = %s
            ORDER BY symbol, timestamp_ms DESC 
        ),
        latest_spot AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close as spot_price,
                timestamp
            FROM spot_prices
            WHERE symbol = %s
            ORDER BY symbol, timestamp DESC
        )
        SELECT 
            p.symbol,
            s.spot_price,
            p.perp_price,
            p.timestamp AS last_updated
        FROM latest_perp p
        JOIN latest_spot s ON p.symbol = s.symbol
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol, symbol))
                row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol}. "
        )
    
    perp_price = float(row['perp_price'])
    spot_price = float(row['spot_price'])
    rho        = calculate_rho(perp_price, spot_price)
    metadata   = get_coin_metadata(symbol)
    
    return {
        "symbol":          symbol,
        "display_symbol":  symbol.replace('USDT', ''),
        "name":            metadata['name'],
        "tier":            metadata['tier'],
        "market_cap_rank": metadata['rank'],
        "perp_price":      round(perp_price, 8),
        "spot_price":      round(spot_price, 8),
        "premium_pct":     round((perp_price - spot_price)/spot_price * 100, 4),
        "rho":             round(rho, 4),
        "signal":          get_signal(rho),
        "signal_by_tier":  {
            tier: get_signal(rho, tier) for tier in THRESHOLDS.keys()
        },
        "last_updated":    row['last_updated'].isoformat()
    }
