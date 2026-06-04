import httpx
import os
import numpy as np
import uvicorn
from datetime import datetime, timezone
from jose import jwt, JWTError, jwk
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from database.db_config import SUPABASE_JWKS_URL
from database.timescale import get_connection
from database.supabase import get_supabase_connection

from src.calculate_funding import annualize_funding_rate, get_funding_signal
from src.calculate_rho import (
    calculate_rho,
    get_signal,
    THRESHOLDS,
    KAPPA, IOTA, GAMMA, RISK_FREE_RATE_8HR, PERIODS_PER_YEAR
)
from src.config import ALL_COINS, MARKET_CAP_LOOKUP
from src.telegram_alerts import send_message
from src.update_data import run_price_update, run_funding_rates_update
from src.utils import log_info, log_warn, log_err


# -------------------------------- MARKET CAP DATA --------------------------------------
TIER_MAP_DB_TO_UI = {
    'large_cap': 'LARGE',
    'mid_cap': 'MID', 
    'small_cap': 'SMALL',
    'Unknown': 'SMALL'
}

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
            db_tier = row['market_cap_tier'] or 'Unknown'
            ui_tier = TIER_MAP_DB_TO_UI.get(db_tier, 'SMALL')

            MARKET_CAP_LOOKUP[row['symbol']] = {
                'tier': ui_tier,
                'rank': row['market_cap_rank'] or 9999,
                'name': row['name'] or row['symbol']
            }
            ALL_COINS.append(row['symbol'])

        log_info(f"Loaded {len(MARKET_CAP_LOOKUP)} coins from database")
        return
    
    except Exception as e:
        log_warn(f"Database load failed: {e}. Trying JSON fallback..."
                       f"Using config.py data: {len(MARKET_CAP_LOOKUP)} coins loaded.")


# -------------------------------------- APP SETUP ----------------------------------------------
async def lifespan(app: FastAPI):
    # startup
    log_info("PerpScope API starting up...")
    load_market_cap_data()
    log_info("Startup complete!")

    yield

    # shutdown
    log_info("Cleaning up...")


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
        'tier': 'SMALL',
        'rank': 9999,
        'name': symbol.replace('USDT', '')
    })


@app.get("/")
def root():
    return {
        "message": "PerpScope API is running",
        "endpoints": {
            "Dashboard": [
                "GET  /api/opportunities?threshold=high&tier=all",
                "GET  /api/coins",
                "GET  /api/stats"
            ],
            "Coin Data": [
                "GET  /api/coin/{symbol}",
                "GET  /api/history/{symbol}?days=90",
                "GET  /api/funding/{symbol}?days=90"
            ],
            "Research": [
                "GET  /api/research/summary?days=90"
            ],
            "Automation": [
                "POST /trigger/funding?key=YOUR_SECRET_KEY",
                "POST /trigger/prices?key=YOUR_SECRET_KEY"
            ],
            "Health": [
                "GET  /health"
            ]
        },
        "threshold_tiers": {
            "no_fee": 0.0,
            "low": 0.532,
            "medium": 1.143,
            "high": 1.794
        },
    }


@app.get("/debug/lookup")
async def debug_lookup():
    return {
        "lookup_size": len(MARKET_CAP_LOOKUP),
        "sample": dict(list(MARKET_CAP_LOOKUP.items())[:3]),
        "all_symbols_count": len(ALL_COINS)
    }


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
    tier=Query('all', description="Market cap filter: all|LARGE|MID|SMALL")):
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
    
    # Fetch latest funding rates for each coin
    funding_lookup = {}

    try:
        funding_sql = """
            SELECT DISTINCT ON (symbol)
                symbol,
                funding_rate
            FROM funding_rates
            ORDER BY symbol, timestamp_ms DESC
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(funding_sql)
                funding_rows = cur.fetchall()

        for row in funding_rows:
            funding_lookup[row['symbol']] = float(row['funding_rate'])

    except Exception as e:
        log_err(f"Could not fetch funding rates: {str(e)}")

    # Fetch latest perp + spot price for every coin
    sql = """
        WITH latest_perp AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS perp_price,
                timestamp   AS last_updated
            FROM perp_prices
            WHERE timestamp >= NOW() - INTERVAL '4 hours'
            ORDER BY symbol, timestamp_ms DESC
        ),
        latest_spot AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS spot_price,
                timestamp   AS last_updated
            FROM spot_prices
            WHERE timestamp >= NOW() - INTERVAL '4 hours'
            ORDER BY symbol, timestamp_ms DESC
        )
        SELECT
            p.symbol,
            s.spot_price,
            p.perp_price,
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

        rho          = calculate_rho(perp_price, spot_price)
        signal       = get_signal(rho, threshold)
        funding_rate = funding_lookup.get(symbol, 0.0)

        results.append({
            "symbol":           symbol,
            "display_symbol":   symbol.replace('USDT', ''),
            "name":             metadata['name'],
            "tier":             metadata['tier'],
            "mc_rank":          metadata['rank'],
            "perp_price":       round(perp_price, 8),
            "spot_price":       round(spot_price, 8),
            "premium":          round((perp_price - spot_price) / spot_price * 100, 4),
            "rho_annual":       round(rho, 4),
            "abs_rho":          round(abs(rho), 4),
            "signal":           signal,
            "is_opportunity":   signal != 'NEUTRAL',
            "last_updated":     row['last_updated'].isoformat(),
            "funding_rate":     round(funding_rate, 6),
        })

        # Sorting by opportunities first (using the 'not' to make True values come first),
        # then by abs_rho descending within each group
        results.sort(key=lambda x: (not x['is_opportunity'], -x['abs_rho']))

        # return {
        #     "threshold_tier":    threshold,
        #     "threhold_value":    THRESHOLDS[threshold],
        #     "total_coins":       len(results),
        #     "opportunity_count": sum(1 for r in results if r['is_opportunity']),
        #     "data":              results
        # }

    return results


@app.get("/api/coin/{symbol}")
async def get_coin_detail(symbol):
    """
    This function returns the current details for a specific coin.

    This will be used by the CoinDetail page to show coin details.
    """
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
    
    history_sql = """
        SELECT
            p.close AS perp_price,
            s.close AS spot_price
        FROM perp_prices p
        JOIN spot_prices s
            ON  p.symbol       = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.symbol    = %s
          AND p.timestamp >= NOW() - INTERVAL '90 days'
          AND p.close > 0
          AND s.close > 0
    """

    mean_abs_rho_90d     = 0.0
    pct_time_opportunity = 0.0

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(history_sql, (symbol,))
                hist_rows = cur.fetchall()

        if hist_rows:
            rho_values = [
                calculate_rho(float(r['perp_price']), float(r['spot_price']))
                for r in hist_rows
            ]

            rho_values = [r for r in rho_values if r == r] # Filtering out NaN values

            if rho_values:
                mean_abs_rho_90d = sum(abs(r) for r in rho_values) / len(rho_values)
                above_threshold  = sum(1 for r in rho_values if abs(r) > THRESHOLDS['high'])
                pct_time_opportunity = above_threshold / len(rho_values)

    except Exception as e:
        log_err(f"Could not calculate 90d stats for {symbol}: {e}")
    

    perp_price = float(row['perp_price'])
    spot_price = float(row['spot_price'])
    rho        = calculate_rho(perp_price, spot_price)
    metadata   = get_coin_metadata(symbol)
    
    return {
        "symbol":          symbol,
        "display_symbol":  symbol.replace('USDT', ''),
        "name":            metadata['name'],
        "tier":            metadata['tier'],
        "mc_rank":         metadata['rank'],
        "perp_price":      round(perp_price, 8),
        "spot_price":      round(spot_price, 8),
        "premium":         round((perp_price - spot_price)/spot_price * 100, 4),
        "rho_annual":      round(rho, 4),
        "signal":          get_signal(rho),
        # "signal_by_tier":  {
        #     tier: get_signal(rho, tier) for tier in THRESHOLDS.keys()
        # },
        "mean_abs_rho_90d": round(mean_abs_rho_90d, 4),
        "pct_time_opportunity": round(pct_time_opportunity, 4)
        # "last_updated":    row['last_updated'].isoformat()
    }


@app.get("/api/history/{symbol}")
async def get_coin_history(symbol, days=Query(default=90)):
    """
    This function returns the hourly rho history for one coin over the past
    N days.

    This will be used by the line chart on the CoinDetail page.
    """
    days = max(1, min(int(days), 365))
    symbol = symbol.upper()

    sql = """
        SELECT 
            p.symbol,
            p.close AS perp_price,
            s.close AS spot_price
        FROM perp_prices p
        JOIN spot_prices s
            ON p.symbol = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.symbol = %s
            AND p.timestamp >= NOW() - INTERVAL 'I day' * %s
            AND p.close > 0
            AND s.close > 0
        ORDER BY p.timestamp_ms ASC
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol, days))
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if not rows:
        raise HTTPException(
            status_code=404, 
            detail=f"No historical data for {symbol}"
        )
    
    history = []
    for row in rows:
        rho = calculate_rho(float(row['perp_price']), float(row['spot_price']))
        history.append({
            "date":         row['timestamp'].strftime('%Y-%m-%d'),
            "perp_price":   round(row['perp_price'], 8),
            "spot_price":   round(row['spot_price'], 8),
            "rho":          round(rho, 4),
            "signal":       get_signal(rho)
        })

    rho_values     = [h['rho'] for h in history]
    abs_rho_values = [abs(r) for r in rho_values]

    return {
        "symbol":       symbol,
        "days":         days,
        "data_points":  len(history),
        "summary": {
            "mean_rho":         round(sum(rho_values)/len(rho_values), 4),
            "mean_abs_rho":     round(sum(abs_rho_values)/len(abs_rho_values), 4),
            "max_rho":          round(max(rho_values), 4),
            "min_rho":          round(min(rho_values), 4),
            "pct_opportuinity": round(
                sum(1 for r in rho_values if abs(r) > THRESHOLDS['high']) 
                / len(rho_values) * 100, 1
            )
        },
        "data":         history
    }


@app.get("/api/funding/{symbol}")
async def get_funding_history(
    symbol,
    days=Query(90, ge=1, le=365)
):
    """
    This function returns the raw funding rate history for one coin.
    """
    symbol = symbol.upper()

    sql = """
        SELECT
            timestamp,
            funding_rate
        FROM funding_rates
        WHERE symbol = %s
            AND timestamp >= NOW() - INTERVAL '1 day' * %s
        ORDER BY timestamp_ms ASC
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol, days))
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No funding rate history for {symbol}"
        )
    
    data = []
    for row in rows:
        rate_8hr    = float(row['funding_rate'])
        annualized  = annualize_funding_rate(rate_8hr)
        data.append({
            "date":       row['timestamp'].strftime('%Y-%m-%d'),
            "funding":    round(rate_8hr, 6),
            "annualized": round(annualized, 2),
            "signal":          get_funding_signal(annualized)
        })

    rates_ann = [d['rate_annualized'] for d in data]

    return {
        "symbol":      symbol,
        "days":        days,
        "data_points": len(data),
        "summary": {
            "mean_annualized":  round(sum(rates_ann)/len(rates_ann), 2),
            "max_annualized":   round(max(rates_ann), 2),
            "min_annualized":   round(min(rates_ann), 2),
        },
        "data":        data
    }


@app.get("/api/research/summary")
async def get_research_summary(days=Query(default=90)):
    """
    This function returns aggregate rho statistics grouped by market cap tier.
    """
    days = max(7, min(int(days), 365))

    sql = """
        SELECT
            p.symbol,
            AVG(ABS(
                (p.close - s.close) / NULLIF(p.close, 0)
            )) AS mean_premium,
            COUNT (*) AS n_observations
        FROM perp_prices p
        JOIN spot_prices s
            ON p.symbol = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.timestamp >= NOW() - INTERVAL '1 day' * %s
            AND p.close > 0
            AND s.close > 0
        GROUP BY p.symbol
        HAVING COUNT(*) >= 5
        ORDER BY p.symbol
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (days,))
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    results = []
    for row in rows:
        symbol       = row['symbol']
        mean_premium = float(row['mean_premium'] or 0)
        metadata     = get_coin_metadata(symbol)

        tier = metadata['tier'] if metadata['tier'] != 'Unknown' else 'SMALL'
        rank = metadata['rank']

        sign_val = float(np.sign(IOTA - RISK_FREE_RATE_8HR))
        mean_rho = (KAPPA * mean_premium + sign_val * GAMMA - RISK_FREE_RATE_8HR) * PERIODS_PER_YEAR

        results.append({
            "symbol":          symbol.replace('USDT', ''),
            "name":            metadata['name'],
            "tier":            tier,
            "rank":            rank,
            "mean_abs_rho":    round(abs(mean_rho), 4),
        })

    results.sort(key=lambda x: x['rank'])

    tier_groups = {}
    for r in results:
        tier = r['tier']
        if tier not in tier_groups:
            tier_groups[tier] = []
        tier_groups[tier].append(r['mean_abs_rho'])

    tiers_array = []
    small_rhos = []
    large_rhos = []
    
    for tier, values in tier_groups.items():
        mean_val = round(np.mean(values), 4)
        tiers_array.append({
            "tier": tier,
            "count": len(values),
            "mean_abs_rho": mean_val,
            "max_abs_rho": round(max(values), 4)
        })
        
        if tier == "SMALL":
            small_rhos = values
        elif tier == "LARGE":
            large_rhos = values
    
    ratio_small_large = 1.0
    if large_rhos and small_rhos:
        ratio_small_large = round(np.mean(small_rhos) / np.mean(large_rhos), 4)

    return {
        "ratio_small_large": ratio_small_large,
        "tiers": tiers_array,
        "scatter": results    
    }


@app.get("/api/stats")
async def get_market_stats():
    """
    This function returns the overall market statistics for the dashboard stats bar.
    """
    sql = """
        WITH latest_perp AS (
            SELECT DISTINCT ON (symbol)
                symbol, close AS perp_price
            FROM perp_prices
            ORDER BY symbol, timestamp_ms DESC
        ),
        latest_spot AS (
            SELECT DISTINCT ON (symbol)
                symbol, close AS spot_price
            FROM spot_prices
            ORDER BY symbol, timestamp_ms DESC
        )
        SELECT p.symbol, p.perp_price, s.spot_price
        FROM latest_perp  p
        JOIN latest_spot  s ON p.symbol = s.symbol
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    if not rows:
        return {
            "total_coins":       0,
            "opportunities":     0,
            "mean_rho":          0,
            "small_large_ratio": 0
        }

    rho_by_tier = {"LARGE": [], "MID": [], "SMALL": []}
    all_rho     = []
    opp_count   = 0

    for row in rows:
        symbol = row['symbol']
        rho    = calculate_rho(float(row['perp_price']), float(row['spot_price']))
        meta   = get_coin_metadata(symbol)
        tier   = meta['tier']

        all_rho.append(rho)

        if abs(rho) > THRESHOLDS['high']:
            opp_count += 1

        if tier in rho_by_tier:
            rho_by_tier[tier].append(rho)

    mean_rho   = sum(all_rho) / len(all_rho) if all_rho else 0
    small_mean = sum(rho_by_tier['SMALL']) / len(rho_by_tier['SMALL']) if rho_by_tier['SMALL'] else 0
    large_mean = sum(rho_by_tier['LARGE']) / len(rho_by_tier['LARGE']) if rho_by_tier['LARGE'] else 0
    ratio      = round(small_mean / large_mean, 2) if large_mean else 0

    return {
        "coins_monitored":       len(rows),
        "active_opportunities":  opp_count,
        "mean_rho":              round(mean_rho, 4),
        "small_large_ratio":     ratio,
        "tier_counts": {
            tier: len(vals)
            for tier, vals in rho_by_tier.items()
        }
    }


@app.get("/debug/prices/{symbol}")
async def debug_prices(symbol):
    symbol = symbol.upper()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT close, timestamp, timestamp_ms
                FROM perp_prices
                WHERE symbol = %s
                ORDER BY timestamp DESC
                LIMIT 5
            """, (symbol,))
            p_rows = cur.fetchall()

            cur.execute("""
                SELECT close, timestamp, timestamp_ms
                FROM spot_prices
                WHERE symbol = %s
                ORDER BY timestamp_ms DESC
                LIMIT 5
            """, (symbol,))
            s_rows = cur.fetchall()

    return {
        "symbol": symbol,
        "latest_perp": [dict(r) for r in p_rows],
        "latest_spot": [dict(r) for r in s_rows]
    }


# ------------------------------------------- AUTOMATION ENDPOINTS ------------------------------------
def verify_cron_secret(key):
    """
    This function verifies that the automation request came from 
    my cron job and raises HTTP 403 if the key is wrong or missing.
    """
    expected_key = os.getenv('CRON_SECRET')

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET environment variable not configured"
        )
    
    if key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid secret key"
        )
    

@app.post("/trigger/funding")
async def trigger_funding_update(
    background_tasks: BackgroundTasks,
    key=Query(..., description="Secret key for authorization")
):
    """
    This function is triggered by cron-job every 8hrs
    for funding rates update.
    """
    verify_cron_secret(key)
    background_tasks.add_task(run_funding_rates_update)
    log_info("Funding rate update triggered by cron-job")

    return {
        "status":   "accepted",
        "message":  "Funding rate update started in background",
        "pipeline": "funding"
    }


@app.post("/trigger/prices")
async def trigger_price_update(
    background_tasks: BackgroundTasks,
    key=Query(..., description="Secret key for authorization")
):
    """
    This function is triggered by cron-job every hour
    to update perp and spot prices.
    """
    verify_cron_secret(key)
    background_tasks.add_task(run_price_update)
    log_info("Perp and spot prices updates triggered by cron-job")

    return {
        "status":   "accepted",
        "message":  "Perp and spot prices updates started in background",
        "pipeline": "prices"
    }


@app.get("/health")
async def health_check():
    """
    This function is called by cron-job every 10 mins to keep Render warm.
    """
    db_status = "unknown"

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status":       "ok",
        "database":     db_status,
        "coins_loaded": len(MARKET_CAP_LOOKUP),
        "timestamp":    datetime.now(timezone.utc).isoformat()
    }


# --------------------------- USER MANAGEMENT ------------------------------
security = HTTPBearer()

_jwks_cache = None

async def get_jwks():
    """
    This function fetches JWKS from supabase endpoint without caching.
    """
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            response = await client.get(SUPABASE_JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()

    return _jwks_cache


def get_signing_key(kid: str, jwks_data: dict):
    """
    This function extracts the public key for the given key ID
    """
    for key in jwks_data.get("keys", []):
        if key.get("kid") == kid:
            return jwk.construct(key).to_pem()
    raise ValueError(f"Key with kid {kid} not found")


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    This function verifies the Supabase JWT usin JWKS
    """
    token = credentials.credentials

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Invalid token: missing kid")
        
        jwks_data = await get_jwks()
        signing_key = get_signing_key(kid, jwks_data)

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256"],
            options={"verify_aud": False}
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user_db_id(user=Depends(get_current_user)):
    """
    This function gets the internal database ID from the users table
    for the currently authenticated user.
    """
    supabase_uid = user.get("sub")

    sql = """
        SELECT
            id, 
            email,
            plan,
            telegram_chat_id
        FROM users
        WHERE supabase_user_id = %s
            AND is_active = true
    """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (supabase_uid,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="User not found in database"
        )
    
    return dict(row)


@app.get("/api/user/profile")
async def get_profile(user=Depends(get_current_user_db_id)):
    """
    This function returns the current user's profile.
    """
    return {
        "id":                 user['id'],
        "email":              user['email'],
        "plan":               user['plan'],
        "telegram_connected": user['telegram_chat_id'] is not None,
    }


@app.post("/api/user/telegram")
async def connect_telegram(body: dict = Body(...), 
                           user=Depends(get_current_user_db_id)
):
    """
    This function saves the user's telegram chat id.
    """
    chat_id = body.get("chat_id", "").strip()

    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    
    sql = """
        UPDATE users
        SET telegram_chat_id = %s
        WHERE id = %s
    """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, user['id']))
        conn.commit()

    from telegram_alerts import send_message
    send_message(chat_id, (
        "✅ *PerpScope Telegram connected!*\n\n"
        "You will receive alerts here when opportunities are detected.\n"
        "Manage alerts at: perpscope-frontend.nwosudavid13.workers.dev/account"
    ))

    return {"status": "ok", "message": "Telegram connected"}


@app.get("/api/user/telegram")
async def get_telegram_status(user=Depends(get_current_user_db_id)):
    """
    This function returns whether the user has connected Telegram.
    """
    return {
        "connected": user['telegram_chat_id'] is not None,
        "chat_id":   user['telegram_chat_id'],
    }


# ------------------------------ ALERT MANAGEMENT -------------------------------
@app.get("/api/user/alerts")
async def get_alerts(user=Depends(get_current_user_db_id)):
    """This function returns all alerts for the current user"""
    sql = """
        SELECT
            id,
            symbol, 
            market_cap_tier,
            threshold_tier,
            min_rho,
            is_active,
            created_at,
            last_triggered
        FROM user_alerts
        WHERE user_id = %s
        ORDER BY created_at DESC
    """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user['id'],))
            rows = cur.fetchall()

    return [dict(r) for r in rows]


@app.post("/api/user/alerts")
async def create_alert(body: dict = Body(...), 
                       user=Depends(get_current_user_db_id)
):
    """This function creates a new alert for the current user."""
    log_info(f"Alert creation body: {body}")

    symbol = body.get('symbol') or None
    
    tier_raw = body.get('tier') or body.get('market_cap_tier') or 'ALL'
    market_cap_tier = None if tier_raw == 'ALL' else tier_raw

    threshold_raw = (
        body.get('threshold') or
        body.get('threshold_tier') or
        'RETAIL'
    )

    threshold_map = {
        'RETAIL':       'high',
        'FUND':         'medium',
        'INSTITUTION':  'low',
        'MARKET_MAKER': 'no_fee',
        'MM':           'no_fee',
        'HIGH':         'high',
        'MEDIUM':       'medium',
        'LOW':          'low',
        'NO_FEE':       'no_fee',
    }

    threshold_tier = threshold_map.get(threshold_raw.upper(), 'high')

    min_rho_raw = body.get('min_rho')

    if min_rho_raw is None:
        min_rho = 1.0
    else:
        try:
            min_rho = float(min_rho_raw)
        except(TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"min_rho must be a number. Received: {min_rho_raw!r}"
            )
        
        if min_rho < 0:
            raise HTTPException(
                status_code=422,
                detail="min_rho must be positive."
            )
        
        if min_rho > 5.0:
            raise HTTPException(
                status_code=422,
                detail=f"min_rho value {min_rho} seems unusually large. "
                       f"Maximum allowed is 5.0 (500% annualized)."
            )

    if user['plan'] == "free":
        count_sql = "SELECT COUNT(*) as c FROM user_alerts WHERE user_id = %s AND is_active = true"
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, (user['id'],))
                row = cur.fetchone()
        if row['c'] >= 3:
            raise HTTPException(
                status_code=403,
                detail="Free plan limited to 3 active alerts. Upgrade to Pro for unlimited alerts."
            )
        
    sql = """
        INSERT INTO user_alerts
            (user_id, symbol, market_cap_tier, threshold_tier,
            alert_channel, min_rho, is_active)
        VALUES
            (%s, %s, %s, %s, 'telegram', %s, true)
        RETURNING id
    """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                user['id'],
                symbol,
                market_cap_tier,
                threshold_tier,
                min_rho
            ))
            new_id = cur.fetchone()['id']
        conn.commit()

    return {"id": new_id, "status": "created"}


@app.delete("/api/user/alerts/{alert_id}")
async def delete_alert(alert_id, user=Depends(get_current_user_db_id)):
    """
    This function deletes one of the current user's alerts.
    """
    sql = """
        DELETE FROM user_alerts
        WHERE id = %s AND user_id = %s
    """

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (alert_id, user['id']))
        conn.commit()

    return {"status": "deleted"}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram calls this url whenever someone sends a message to the PerpScope bot.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}
    
    message  = body.get('message', {})
    chat_id  = message.get('chat', {}).get('id')
    text     = message.get('text', '')
    username = message.get('from', {}).get('username', 'unknown')

    if not chat_id:
        return {"ok": True}
    
    if '/start' in text:
        reply_text = (
            f"👋 *Welcome to PerpScope Alerts!*\n\n"
            f"Your Chat ID is:\n"
            f"`{chat_id}`\n\n"
            f"Copy this number and paste it into your "
            f"PerpScope account settings at:\n"
            f"perpscope-frontend.nwosudavid13.workers.dev/account\n\n"
            f"You will then receive real-time alerts when "
            f"funding rate opportunities are detected for "
            f"your watched coins."
        )
        send_message(str(chat_id), reply_text)
        log_info(f"Sent chat_id to @{username} ({chat_id})")

    elif '/stop' in text:
        reply_text = (
            f"🛑 *Alerts paused*\n\n"
            f"You will no longer receive PerpScope alerts.\n"
            f"Send /start to resume."
        )
        send_message(str(chat_id), reply_text)
        log_info(f"Paused alerts for @{username}")

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
