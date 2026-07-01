"""
get_market_caps.py - Bybit market cap classifier

This script fetches market rankings from Coingecko and classifies
the altcoin universe into Large/Mid/Small cap tiers. The classification
is used in the research view to compare mispricing behaviour across different
market cap segments
"""

import requests
import json
import os
import time
from datetime import datetime, timezone

from src.config import COINGECKO_BASE_URL
from src.utils import log_info, log_warn, log_err
from backend.database.connection import get_connection


TIER_THRESHOLDS = {
    'LARGE': 20,    # i.e rank 1-20
    'MID':   100,   # i.e rank 21-100
    # everything rank > 100 would be classified as SMALL
}


def classify_tier(rank):
    if rank <= TIER_THRESHOLDS['LARGE']:
        return 'LARGE'
    elif rank <= TIER_THRESHOLDS['MID']:
        return 'MID'
    return 'SMALL'


def fetch_coingecko_rankings(pages=4, per_page=250):
    """
    This function pulls market cap rankings from CoinGecko accross 
    multiple pages.

    250 per page is CoinGecko's max and 4 per page covers top 1000 coins,
    which is enough to get the ranking info we need for out 300 coins
    """
    all_coins = {}

    url = f"{COINGECKO_BASE_URL}/markets"

    for page in range(1, pages + 1):
        try:
            response = requests.get(url, params= {
                'vs_currency':  'usd',
                'order':        'market_cap_desc',
                'per_page':     per_page,
                'page':         page,
                'sparkline':    False
            }, timeout=30)
            data = response.json()

            if not isinstance(data, list):
                log_err(f"CoinGecko page {page} returned unexpected format: {data}")
                continue

            for coin in data:
                symbol = coin['symbol'].upper()
                all_coins[symbol] = {
                    'name': coin['name'],
                    'rank': coin['market_cap_rank'] or 9999
                }
            time.sleep(1.5) # since we're using CoinGecko free tier

        except Exception as e:
            log_err(f"CoinGecko fetch failed on page {page}: {e}")
            continue

    log_info(f"Fetched {len(all_coins)} coins from CoinGecko")
    return all_coins


def update_market_caps():
    """
    This function updates market_cap_rank, market_cap_tier, and name 
    for every active symbol in coin_universe, matching against CoinGecko's
    base symbol (i.e without the 'USDT' suffix).
    """
    cg_data = fetch_coingecko_rankings()
    if not cg_data:
        log_err("No Coingecko data fetched... aborting update")
        return 0
    
    get_symbols_sql = """
        SELECT symbol FROM coin_universe
        WHERE is_active = true
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(get_symbols_sql)
            active_symbols = [row['symbol'] for row in cur.fetchall()]

    updated = 0
    not_found = 0

    update_sql = """
        UPDATE coin_universe
        SET market_cap_rank     = %s,
            market_cap_tier     = %s,
            name                = %s,
            market_cap_updated_at = %s
        WHERE symbol = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            for symbol in active_symbols:
                base = symbol.replace('USDT', '')
                _match = cg_data.get(base)

                if not _match:
                    not_found += 1
                    continue

                tier = classify_tier(_match['rank'])

                cur.execute(update_sql, (
                    _match['rank'],
                    tier,
                    _match['name'],
                    datetime.now(timezone.utc),
                    symbol
                ))
                updated += 1
        conn.commit()

    log_info(f"Market cap update: {updated} symbols updated, "
             f"{not_found} symbols not found on CoinGecko")
    return updated


if __name__ == "__main__":
    update_market_caps()