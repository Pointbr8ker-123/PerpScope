import requests
import json
import os
import time

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import REQUEST_TIMEOUT
from utils import log


def fetch_coingecko_page(page, per_page=250):
    """
    This function fetches one page of market ranking from CoinGecko
    and returns a dictionary of coins or an empty list if request is failed.
    """
    url = "https://api.coingecko.com/api/v3/coins/markets"
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
            log(f"Rate limited on page {page}. Waiting 60 seconds...")
            time.sleep(60)
            return fetch_coingecko_page(page, per_page)
        
        if response.status_code != 200:
            log(f"Error on page {page}: status {response.status_code}")
            return []
        
        return response.json()
    
    except Exception as e:
        log(f"Request failed on page {page}: {e}")
        return []
    

def fetch_all_rankings(max_coins=1000):
    """
    This function fetches market cap rankings for the top 1000 coins.
    """
    per_page = 250
    pages = max_coins // per_page # probably 4 pages

    all_coins = []

    for page in range(1, pages + 1):
        log(f"Fetching CoinGecko page {page}/{pages}...")
        coins = fetch_coingecko_page(page, per_page)

        if not coins:
            log(f"No data returned for page {page}, stopping...")
            break

        all_coins.extend(coins)
        time.sleep(6)

    log(f"Fetched {len(all_coins)} coins from CoinGecko")
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
            'symbol': cg_symbol
        }

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
                'coingecko_id': lookup.get(s, {}).get('coingecko_id', None)
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
    log(f"Product universe has {len(product_universe)} coins to classify")

    # Fetching market cap rankings from CoinGecko
    log(f"Fetching market cap rankings from CoinGecko...")
    coingecko_coins = fetch_all_rankings(max_coins=1000)

    # Building the symbol matching lookup
    log(f"\nBuilding symbol matching lookup...")
    lookup = build_ranking_lookup(coingecko_coins)
    log(f"Lookup covers {len(lookup)} Bybit-compatible coins.")

    # Classifying the Product universe coins
    log("\nClassifying research universe by market cap...")
    large, mid, small, unmatched = classify_by_market_cap(
        lookup, product_universe
    )
    
    # Save results
    save_market_cap_classification(lookup, large, mid, small, unmatched)
    
    # log summary
    log("\n" + "="*50)
    log("CLASSIFICATION RESULTS")
    log("="*50)
    log(f"Large cap  (rank 1-20):   {len(large)} coins")
    for s in large:
        log(f"    {s:<15} rank {lookup[s]['rank']}")
    
    log(f"\nMid cap    (rank 21-100): {len(mid)} coins")
    log(f"Small cap  (rank 101+):   {len(small)} coins")
    
    if unmatched:
        log(f"\nUnmatched coins ({len(unmatched)}) — review manually:")
        for s in unmatched:
            log(f"    {s}")
    
    log(f"\nSaved to market_cap_classification.json")


if __name__ == "__main__":
    run_classification()