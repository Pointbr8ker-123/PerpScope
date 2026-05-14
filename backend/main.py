import os
import sys
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from config import SRC_DIR, ALL_COINS, MARKET_CAP_LOOKUP

sys.path.insert(0, SRC_DIR)

from backend.database.supabase import get_connection
from calculate_rho import (
    calculate_rho,
    get_signal,
    THRESHOLDS,
    KAPPA, IOTA, GAMMA, RISK_FREE_RATE_8HR, PERIODS_PER_YEAR
)
from calculate_funding import annualize_funding_rate, get_funding_signal
from update_data import run_price_update, run_funding_rates_update
from utils import log


# -------------------------------- APP SETUP --------------------------------------
app = FastAPI(
    title="PerpScope API",
    description=(
        "Altcoin perpetual futures analytics API."
        "Implements no-arbitrage pricing from He, Manela, Ross & von Wachter (2024)",
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
    This function loads market cap classification
    """

