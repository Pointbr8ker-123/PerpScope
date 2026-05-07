# This script implements the rho(ρ) deviation measure from He, Manela,
# Ross, and von Watcher (2024) "Fundamentals of Perpetual Futures"

# ρ is the annualized deviation of the perpetual futures price from its
# theoretical no-arbitrage fair value (i.e the value of the perpetual if
# everything were fair)

# The formular from the paper:
#     ρ = κ × (F - S)/F + sign(ι - r) × γ - r

# Where:
#   F = perpetual futures price (mark price)
#   S = spot price (index price)  
#   κ = 1 (Binance/Bybit premium scaling constant)
#   ι = 0.0001 (base interest rate per 8hrs = 0.01%)
#   γ = 0.0005 (clamp width = 0.05%)
#   r = risk-free interest rate (we use stablecoin lending rate)

# When ρ > trading_cost_threshold → short perp, long spot
# When ρ < -trading_cost_threshold → long perp, short spot
# When |ρ| < threshold → no opportunity

import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MARKET_CAP_LOOKUP
from database import get_connection


# ----------------Bybit Funding rate parameters-------------------------
KAPPA   = 1.0
IOTA    = 0.0001
GAMMA   = 0.0005

# Risk-free rate (He et al. uses DeFi stable coin lending rates from Aave)
RISK_FREE_RATE_8HR  = 0.0000548

PERIODS_PER_YEAR    = 1095   # i.e 3 funding periods/day x 365 days/year


# ------------------- Trading Cost Thresholds --------------------------
# Annualized ρ thresholds adapted from Table 3 in He et al. for Bybit's 
# fee structure

THRESHOLDS = {
    'no_fee':   0.000, # for Market makers
    'low':      0.532, # for Large institutional traders
    'medium':   1.143, # for small funds
    'high':     1.794, # for Retail traders
}


# ---------------------------- rho(ρ) Calculation ------------------------
def calculate_rho(futures_price, spot_price, risk_free_rate=RISK_FREE_RATE_8HR):
    """
    This function calculates the annualized rho deviation for a single observation.

    Parameters:
        futures_price:  perpetual futures mark price (F)
        spot_price:     spot index price (S)
        risk_free_rate: 8-hour risk-free rate(r)

    Returns:
        rho (float): annualized % deviation from no-arbitrage fair value

    Formula -> from He et al. (2024), Equation 21:
        ρ_period = κ × (F - S)/F + sign(ι - r) × γ - r
        ρ_annualized = ρ_period × 1095
    """
    if futures_price <= 0 and spot_price <= 0:
        return np.nan
    
    # Premium index: (F - S)/F
    premium_index = (futures_price - spot_price) / futures_price

    # sign(ι - r) which determines the side of the funding clamp we're on
    sign_iota_minus_r = np.sign(IOTA - risk_free_rate)

    # ρ per 8-hr period 
    rho_per_period = (
        KAPPA * premium_index 
        + sign_iota_minus_r * GAMMA
        - risk_free_rate
    )

    return rho_per_period * PERIODS_PER_YEAR


def get_signal(rho, threshold_tier='high'):
    """
    This function converts a rho value into a trading signal string.
    """
    if np.isnan(rho):
        return 'NEUTRAL'
    
    threshold = THRESHOLDS.get(threshold_tier, THRESHOLDS['high'])

    if rho > threshold:
        return 'SHORT_PERP_LONG_SPOT'
    elif rho < -threshold:
        return 'LONG_PERP_SHORT_SPOT'
    else:
        return 'NEUTRAL'
    

# ----------------------------- Database Query Functions ---------------------------------
