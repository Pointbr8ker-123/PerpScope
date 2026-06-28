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

from src.config import REQUEST_TIMEOUT, COINGECKO_BASE_URL
from src.utils import log_info, log_warn, log_err


def fetch_coingecko_page(page, per_page=250):
    """
    This function fetches one page of market ranking from CoinGecko
    and returns a dictionary of coins or an empty list if request is failed.
    """
    url = f"{COINGECKO_BASE_URL}/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "sparkline": False
    }

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

        if response.status_code == 429:
            log_info(f"Rate limited on page {page}. Waiting 60 seconds...")
            time.sleep(60)
            return fetch_coingecko_page(page, per_page)
        
        if response.status_code != 200:
            log_err(f"Error on page {page}: status {response.status_code}")
            return []
        
        return response.json()
    
    except Exception as e:
        log_warn(f"Request failed on page {page}: {e}")
        return []


def fetch_all_rankings(max_coins=5000):
    """
    This function fetches market cap rankings for the top 1000 coins.
    """
    per_page = 250
    pages = max_coins // per_page # probably 4 pages

    all_coins = []

    for page in range(1, pages + 1):
        log_info(f"Fetching CoinGecko page {page}/{pages}...")
        coins = fetch_coingecko_page(page, per_page)

        if not coins:
            log_warn(f"No data returned for page {page}, stopping...")
            break

        all_coins.extend(coins)
        time.sleep(6)

    log_info(f"Fetched {len(all_coins)} coins from CoinGecko")
    return all_coins


def build_ranking_lookup(coingecko_coins):
    """
    This function builds a lookup dictionary from the coingecko data
    which we will convert to bybit symbol format for later comparisons
    """
    lookup = {}

    for i, coin in enumerate(coingecko_coins):
        cg_symbol = coin['symbol'].upper()
        cg_id = coin['id']

        # CoinGecko uses "BTC" while Bybit uses "BTCUSDT"
        # This helps map one to the other so we can match market cap data
        bybit_symbol = cg_symbol + 'USDT'

        if bybit_symbol in lookup:
            existing_rank = lookup[bybit_symbol]['rank']
            new_rank = i + 1
            if new_rank < existing_rank:
                pass
            else:
                continue

        lookup[bybit_symbol] = {
            'rank': i + 1,
            'market_cap': coin['market_cap'] or 0,
            'name': coin['name'],
            'coingecko_id': cg_id,
            'symbol': cg_symbol,
            # 'launch_time_ms': None
        }
    print(json.dumps(coingecko_coins[0], indent=2))

    return lookup


def classify_by_market_cap(lookup, product_universe):
    """
    This function takes all the coins in our product universe and classifies them
    into market cap tier using the CoinGecko lookup from the function above.

    Tiers:
    - Large cap: rank 1-20
    - Mid cap: rank 21-100
    - Small cap: rank 100+
    - Unmatched = No coingecko data found
    """

    large_cap = []
    mid_cap = []
    small_cap = []
    unmatched = []

    for bybit_symbol in product_universe:
        if bybit_symbol in lookup:
            rank = lookup[bybit_symbol]['rank']

            if rank <= 20:
                large_cap.append(bybit_symbol)
            elif rank <= 100:
                mid_cap.append(bybit_symbol)
            else:
                small_cap.append(bybit_symbol)
        else:
            unmatched.append(bybit_symbol)

    return large_cap, mid_cap, small_cap, unmatched


def save_market_cap_classification(lookup, large, mid, small, unmatched):
    """
    This function saves te full classification to a json file
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(base_dir, 'market_cap_classification.json')

    def build_group_details(symbols):
        return [
            {
                'symbol': s,
                'name': lookup.get(s, {}).get('name', 'Unknown'),
                'rank': lookup.get(s, {}).get('rank', 9999),
                'market_cap': lookup.get(s, {}).get('market_cap', 0),
                'coingecko_id': lookup.get(s, {}).get('coingecko_id', None),
                # 'launch_time_ms': lookup.get(s, {}).get('launch_time_ms', None)
            }
            for s in sorted(symbols, key=lambda x: lookup.get(x, {}).get('rank', 9999))
        ]
    
    classification = {
        'generated_at': __import__('datetime').datetime.now().isoformat(),
        'large_cap': build_group_details(large),
        'mid_cap': build_group_details(mid),
        'small_cap': build_group_details(small),
        'unmatched': build_group_details(unmatched),
        'summary': {
            'large_cap_count': len(large),
            'mid_cap_count': len(mid),
            'small_cap_count': len(small),
            'unmatched_count': len(unmatched),
            'total_classification': len(large) + len(mid) + len(small)
        }
    }

    with open(output_path, 'w') as f:
        json.dump(classification, f, indent=2)


def run_classification():
    """
    This is the main function that joins everything together
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    universe_path = os.path.join(base_dir, 'coin_universe.json')

    with open(universe_path, 'r') as f:
        universe = json.load(f)

    product_universe = universe['product_universe']
    log_info(f"Product universe has {len(product_universe)} coins to classify")

    # Fetching market cap rankings from CoinGecko
    log_info(f"Fetching market cap rankings from CoinGecko...")
    coingecko_coins = fetch_all_rankings(max_coins=5000)

    # Building the symbol matching lookup
    log_info(f"\nBuilding symbol matching lookup...")
    lookup = build_ranking_lookup(coingecko_coins)
    log_info(f"Lookup covers {len(lookup)} Bybit-compatible coins.")

    # Classifying the Product universe coins
    log_info("\nClassifying research universe by market cap...")
    large, mid, small, unmatched = classify_by_market_cap(
        lookup, product_universe
    )
    
    # Save results
    save_market_cap_classification(lookup, large, mid, small, unmatched)
    
    # log_info summary
    log_info("\n" + "="*50)
    log_info("CLASSIFICATION RESULTS")
    log_info("="*50)
    log_info(f"Large cap  (rank 1-20):   {len(large)} coins")
    for s in large:
        log_info(f"    {s:<15} rank {lookup[s]['rank']}")
    
    log_info(f"\nMid cap    (rank 21-100): {len(mid)} coins")
    log_info(f"Small cap  (rank 101+):   {len(small)} coins")
    
    if unmatched:
        log_info(f"\nUnmatched coins ({len(unmatched)}) — review manually:")
        for s in unmatched:
            log_info(f"    {s}")
    
    log_info(f"\nSaved to market_cap_classification.json")


if __name__ == "__main__":
    run_classification()