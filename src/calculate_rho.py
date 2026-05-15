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
from backend.database.timescale import get_connection


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
    if futures_price <= 0 or spot_price <= 0:
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
def get_latest_prices(symbols=None):
    """
    This function fetches the most recent perp_price-spot_price pair for each symbol
    by joining on timestamp_ms. 
    """
    if symbols:
        placeholders = ', '.join(['%s'] * len(symbols))
        symbol_clause = f"AND p.symbol IN ({placeholders})"
        params = tuple(symbols) * 2
    else:
        symbol_clause = ""
        params = ()

    sql = f"""
        WITH latest_perp AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS perp_price,
                timestamp   AS perp_time
            FROM perp_prices
            WHERE 1=1 {symbol_clause}
            ORDER BY symbol, timestamp_ms DESC
        ),
        latest_spot AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                close       AS spot_price,
                timestamp   AS spot_time
            FROM spot_prices
            WHERE 1=1 {symbol_clause}
            ORDER BY symbol, timestamp_ms DESC
        )
        SELECT
            p.symbol,
            p.perp_price,
            s.spot_price,
            p.perp_time,
            s.spot_time
        FROM latest_perp p
        JOIN latest_spot s ON p.symbol = s.symbol
        ORDER BY p.symbol
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params if params else None)
            rows = cur.fetchall()
    
    if not rows:
        return pd.DataFrame(columns=['symbol', 'perp_price', 'spot_price',
                                     'perp_time', 'spot_time'])
    
    return pd.DataFrame([dict(r) for r in rows])


def  get_historical_rho(symbol, days=90):
    """
    This function calculates historical rho for a single coin over the past
    N days. Would be used by the coin detail chart page.
    """
    sql = """
        SELECT 
            p.timestamp,
            p.close     AS perp_price,
            s.close     AS spot_price
        FROM perp_prices p
        JOIN spot_prices s
            ON p.symbol        = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.symbol = %s
        AND p.timestamp >= NOW() - INTERVAL '1 day' * %s
        ORDER BY p.timestamp_ms ASC
    """
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (symbol, days))
            rows = cur.fetchall()

    if not rows:
        return pd.DataFrame(columns=['timestamp', 'perp_price', 'spot_price',
                            'rho', 'signal'])
    
    df = pd.DataFrame([dict(r) for r in rows])

    df['rho'] = df.apply(
        lambda row: calculate_rho(row['perp_price'], row['spot_price']),
        axis=1
    )

    df['signal'] = df['rho'].apply(get_signal)

    return df


def calculate_current_opportunities(threshold_tier='high'):
    """
    This is the main function that the app's dashboard leaderboard calls.
    It fetches current prices for all the coins, computes rho, attaches 
    market cap metadata from MARKET_CAP_LOOKUP, and returns a sorted Dataframe
    with opportunities ranked first (i.e largest |rho| at the top).
    """
    prices_df = get_latest_prices()

    if prices_df.empty:
        return pd.DataFrame()
    
    # Compute rho to derive a signal
    prices_df['rho'] = prices_df.apply(
        lambda row: calculate_rho(row['perp_price'], row['spot_price']),
        axis=1
    )

    prices_df['abs_rho'] = prices_df['rho'].abs()

    prices_df['signal'] = prices_df['rho'].apply(
        lambda r: get_signal(r, threshold_tier)
    )

    # Attach market cap metadata
    prices_df['tier'] = prices_df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('tier', 'Unknown')
    )

    prices_df['rank'] = prices_df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('rank', 9999)
    )

    prices_df['name'] = prices_df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('name', s)
    )

    # Sort by opportunities, then by |rho|
    prices_df['is_opportunity'] = prices_df['signal'] != 'NEUTRAL'
    prices_df = prices_df.sort_values(
        ['is_opportunity', 'abs_rho'],
        ascending=[False, False]
    )

    prices_df = prices_df.drop(columns=['is_opportunity'])
    prices_df = prices_df.reset_index(drop=True)

    return prices_df


def get_market_cap_comparison_data(days=90):
    """
    Calculates mean |ρ| per coin over the past N days, grouped by market cap
    tier. Used by the research / academic comparison chart.
    """
    sql = """
        SELECT
            p.symbol,
            p.close     AS perp_price,
            s.close     AS spot_price,
            p.timestamp
        FROM perp_prices p
        JOIN spot_prices s
            ON  p.symbol       = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.timestamp >= NOW() - INTERVAL '1 day' * %s
        ORDER BY p.symbol, p.timestamp_ms ASC
    """
 
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (days,))
            rows = cur.fetchall()
 
    if not rows:
        return pd.DataFrame()
 
    df = pd.DataFrame([dict(r) for r in rows])
 
    # Compute ρ
    df['rho'] = df.apply(
        lambda row: calculate_rho(row['perp_price'], row['spot_price']),
        axis=1
    )
    df['abs_rho'] = df['rho'].abs()
 
    # Attach metadata
    df['tier'] = df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('tier', 'Unknown')
    )
    df['rank'] = df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('rank', 9999)
    )
    df['name'] = df['symbol'].map(
        lambda s: MARKET_CAP_LOOKUP.get(s, {}).get('name', s)
    )
 
    # Aggregate by coin 
    summary = df.groupby(['symbol', 'tier', 'rank', 'name']).agg(
        mean_abs_rho   = ('abs_rho', 'mean'),
        std_rho        = ('rho',     'std'),
        mean_rho       = ('rho',     'mean'),
        n_observations = ('rho',     'count')
    ).reset_index()
 
    summary = summary[summary['n_observations'] >= 30]
    summary = summary.sort_values('rank')
 
    return summary


if __name__ == "__main__":
    print("Testing ρ calculation...")

    test_rho = calculate_rho(101_000, 100_000)
    print(f"BTC test (1% premium): ρ = {test_rho:.4f} ({test_rho*100:.2f}% annualized)")
    print(f"Signal: {get_signal(test_rho)}")

