import os
import sys
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware

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


# ------------------------------- LOGGING --------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# -------------------------------- APP SETUP --------------------------------------
app = FastAPI(
    title="PerpScope API",
    description=(
        "Altcoin perpetual futures analytics API."
        "Implements no-arbitrage pricing from He, Manela, Ross & von Wachter (2024)"
    ),
    version="1.0.0"
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
