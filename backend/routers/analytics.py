# backend/routers/analytics.py
#
# Market data endpoints consumed by the React frontend.
# All endpoints are public — no authentication required.
#
# Endpoints:
#   GET /api/stats            -> dashboard summary metrics
#   GET /api/opportunities    -> ranked opportunity table
#   GET /api/coins            -> full coin list for dropdowns
#   GET /api/coin/{symbol}    -> single coin current detail
#   GET /api/history/{symbol} -> historical ρ for charts
#   GET /api/funding/{symbol} -> funding rate history for charts
#   GET /api/research/summary -> cross-sectional tier analysis

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from backend.database.connection import get_connection
from src.calculate_funding import annualize_funding_rate, get_funding_signal
from src.calculate_rho import (
    calculate_rho,
    get_signal,
    THRESHOLDS,
    KAPPA, IOTA, GAMMA, RISK_FREE_RATE_8HR, PERIODS_PER_YEAR
)
from src.utils import log_err, sanitize_floats
from backend.database.db_config import get_coin_metadata, get_all_symbols


router = APIRouter(prefix="/api", tags=["analytics"])


# --------------------------- ENDPOINTS -----------------------------------------
@router.get("/coins")
async def get_all_coins():
    """
    This function returns the full list of monitored coins with metadata.
    """
    coins = []
    
    for symbol in get_all_symbols():
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


@router.get("/opportunities")
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

    return sanitize_floats(results)


@router.get("/coin/{symbol}")
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
    
    return sanitize_floats({
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
        "mean_abs_rho_90d": round(mean_abs_rho_90d, 4),
        "pct_time_opportunity": round(pct_time_opportunity, 4)
    })


@router.get("/history/{symbol}")
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
            s.close AS spot_price,
            p.timestamp
        FROM perp_prices p
        JOIN spot_prices s
            ON p.symbol = s.symbol
            AND p.timestamp_ms = s.timestamp_ms
        WHERE p.symbol = %s
            AND p.timestamp >= NOW() - INTERVAL '1 day' * %s
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

        # Skip corrupted data
        if rho != rho:
            continue

        history.append({
            "date":         row['timestamp'].strftime('%Y-%m-%d'),
            "perp_price":   round(row['perp_price'], 8),
            "spot_price":   round(row['spot_price'], 8),
            "rho":          round(rho, 4),
            "signal":       get_signal(rho)
        })

    rho_values     = [h['rho'] for h in history]
    abs_rho_values = [abs(r) for r in rho_values]

    return sanitize_floats({
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
    })


@router.get("/funding/{symbol}")
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

    return sanitize_floats({
        "symbol":      symbol,
        "days":        days,
        "data_points": len(data),
        "summary": {
            "mean_annualized":  round(sum(rates_ann)/len(rates_ann), 2),
            "max_annualized":   round(max(rates_ann), 2),
            "min_annualized":   round(min(rates_ann), 2),
        },
        "data":        data
    })


@router.get("/research/summary")
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
    
    # Calculate ratio of average |ρ| for Small vs Large cap coins.
    # This is the key research finding: small caps show larger deviations.
    ratio_small_large = 1.0
    if large_rhos and small_rhos:
        ratio_small_large = round(np.mean(small_rhos) / np.mean(large_rhos), 4)

    return sanitize_floats({
        "ratio_small_large": ratio_small_large,
        "tiers": tiers_array,
        "scatter": results    
    })


@router.get("/stats")
async def get_market_stats():
    """
    This function returns the overall market statistics for the dashboard stats bar.
    """
    sql = """
        WITH latest_perp AS (
            SELECT DISTINCT ON (p.symbol)
                p.symbol, p.close AS perp_price
            FROM perp_prices p
            JOIN coin_universe cu ON cu.symbol = p.symbol
            WHERE p.close > 0
                AND cu.is_active = true
            ORDER BY p.symbol, p.timestamp_ms DESC
        ),
        latest_spot AS (
            SELECT DISTINCT ON (s.symbol)
                s.symbol, s.close AS spot_price
            FROM spot_prices s
            JOIN coin_universe cu ON cu.symbol = s.symbol
            WHERE s.close > 0
                AND cu.is_active = true
            ORDER BY s.symbol, s.timestamp_ms DESC
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

        # Skip NaN values - they indicate corrupted data
        if rho != rho:
            continue

        all_rho.append(rho)

        if abs(rho) > THRESHOLDS['high']:
            opp_count += 1

        if tier in rho_by_tier:
            rho_by_tier[tier].append(rho)

    mean_rho   = sum(all_rho) / len(all_rho) if all_rho else 0
    small_mean = sum(rho_by_tier['SMALL']) / len(rho_by_tier['SMALL']) if rho_by_tier['SMALL'] else 0
    large_mean = sum(rho_by_tier['LARGE']) / len(rho_by_tier['LARGE']) if rho_by_tier['LARGE'] else 0
    ratio      = round(small_mean / large_mean, 2) if large_mean else 0

    return sanitize_floats({
        "coins_monitored":       len(rows),
        "active_opportunities":  opp_count,
        "mean_rho":              round(mean_rho, 4),
        "small_large_ratio":     ratio,
        "tier_counts": {
            tier: len(vals)
            for tier, vals in rho_by_tier.items()
        }
    })
