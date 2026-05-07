import requests
import json
import os
from datetime import datetime, timezone
from config import BASE_URL


def get_all_linear_perpetuals():
    """
    This function gets every active linear (USDT-settled) perpetual futures 
    contract from Bybit.
    Returns a list of dictionaries with symbol info.
    """

    url = f"{BASE_URL}/v5/market/instruments-info"

    all_symbols = []
    cursor = None

    while True:
        params = {
            "category": "linear",
            "status": "Trading",
            "limit": 1000
        }

        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data['retCode'] != 0:
                print(f"API Error: {data['retMsg']}")

            instruments = data['result']['list']

            for item in instruments:
                symbol = item['symbol']
                if symbol.endswith('USDT') and item['contractType'] == "LinearPerpetual":
                    all_symbols.append({
                        "symbol": symbol,
                        "launch_time_ms": int(item.get('launchTime', 0)),
                        "status": item['status']
                    })

            next_cursor = data['result'].get('nextPageCursor', '')
            if not next_cursor:
                break

            cursor = next_cursor

        except Exception as e:
            print(f"Error Fetching Instruments: {e}")
            break

    return all_symbols


def get_all_spot_symbols():
    """
    This function gets every active spot trading pair.
    We use this to check which perpetuals also have a spot market.
    """

    url = f"{BASE_URL}/v5/market/instruments-info"

    spot_symbols = set()

    params = {
        "category": "spot",
        "status": "Trading",
        "limit": 1000
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data['retCode'] == 0:
            for item in data['result']['list']:
                spot_symbols.add(item['symbol'])

    except Exception as e:
        print(f"Error fetching symbols: {e}")

    return spot_symbols


def classify_coins(perpetuals, spot_symbols):
    """
    This function seperates the coins into:
    - research_universe i.e has 18+ months of history
    - product_universe i.e has perpetual and spot, but also includes those 
      with less than 18 months of history (research_universe + others)
    - perp_only i.e has perpetual but no spot (not useful)

    and returns them (the first two) as lists containing the symbols of these coins.
    """

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    eighteen_months = 18 * 30 * 24 * 60 * 60 * 1000
    cut_off = now_ms - eighteen_months

    research_universe = []
    the_rest = []

    for coin in perpetuals:
        symbol = coin['symbol']
        launch_ms = coin['launch_time_ms']

        has_spot = symbol in spot_symbols
        old_enough = launch_ms < cut_off and launch_ms > 0

        if not has_spot:
            continue
        elif old_enough:
            research_universe.append(symbol)
        else:
            the_rest.append(symbol)

    product_universe = research_universe + the_rest
    return research_universe, product_universe


def save_universe(research, product):
    """
    This function saves the coin universe to a JSON file so config.py can load it.
    """

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(base_dir, 'coin_universe.json')

    universe = {
        'generated_at': datetime.now().isoformat(),
        'research_universe': sorted(research),
        'product_universe': sorted(product)
    }

    with open(output_path, 'w') as f:
        json.dump(universe, f, indent=2)

    print("\nUniverse saved to coin_universe.json")
    print(f"Research universe:     {len(research)} coins")
    print(f"Product universe:      {len(product)} coins")


if __name__ == "__main__":
    print("Step 1: Fetching all linear perpetuals...")
    perpetuals = get_all_linear_perpetuals()
    print(f"Found {len(perpetuals)} linear perpetual contracts")
    
    print("\nStep 2: Fetching all spot symbols...")
    spot_symbols = get_all_spot_symbols()
    print(f"Found {len(spot_symbols)} spot trading pairs")
    
    print("\nStep 3: Classifying coins...")
    research, product = classify_coins(perpetuals, spot_symbols)
    
    print("\nStep 4: Saving universe...")
    save_universe(research, product)

    print("\nSample of research universe:")
    for s in research[:10]:
        print(f"  {s}")
    
    print("\nSample of product universe (newer coins):")
    for s in product[:10]:
        print(f"  {s}")