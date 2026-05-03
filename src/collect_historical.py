import json
import os
import pandas as pd
import random
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    BASE_URL, PRODUCT_UNIVERSE, REQUEST_TIMEOUT,
    SLEEP_BETWEEN_CALLS, SLEEP_BETWEEN_COINS, SLEEP_ON_ERROR,
    KLINE_INTERVAL, HISTORY_START_DAY, HISTORY_START_MONTH,
    HISTORY_START_YEAR, create_data_dir,
    get_funding_path, get_perp_path, get_spot_path
)
from utils import date_to_ms, now_ms, log


# ----------------------FUNDING RATE--------------------------------------------
def fetch_funding_rates_page(symbol, start_ms, end_ms, limit=200):
    """
    This function fetches one page of the funding rate history
    of a particular coin and returns a list of records or None if
    the request failed.
    """
    url = f"{BASE_URL}/v5/market/funding/history"
    params = {
        "category": "linear",
        "symbol": symbol,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        data = response.json()

        if data['retCode'] != 0:
            log(f"API Error for {symbol} funding: {data['retMsg']}")

        return data['result']['list']
    
    except Exception as e:
        log(f"Request Failed for {symbol} funding: {e}")
        return None
    

def collect_funding_rates(symbol, start_ms=None):
    """
    This function collects all the funding rate history for a particular
    symbol (after it has been fetched via the bybit API with the function above)
    from start_ms to now.
    The function saves the results to a csv file and returns the number of
    records collected.
    """
    if start_ms is None:
        start_ms = date_to_ms(
            HISTORY_START_YEAR,
            HISTORY_START_MONTH,
            HISTORY_START_DAY
        )

    end_ms = now_ms()
    all_records = []
    curr_start = start_ms

    # Funding rate interval for 8hrs with a limit of 200 records for each page
    page_size_ms = 200 * 8 * 60 * 60 * 1000

    while curr_start < end_ms:
        curr_end = min(curr_start + page_size_ms, end_ms)

        records = fetch_funding_rates_page(
            symbol,
            curr_start,
            curr_end
        )

        if records is None:
            # Might be as a result of an API error... so wait and try to continue
            time.sleep(SLEEP_ON_ERROR)
            curr_start = curr_end + 1
            continue

        if records:
            all_records.extend(records)

        curr_start = curr_end + 1
        time.sleep(SLEEP_BETWEEN_CALLS)

    if not all_records:
        log(f"No funding rate data found for {symbol}")
        return 0
    
    # Convert all_records to a pandas dataframe
    df = pd.DataFrame(all_records)

    # Renaming columns for clearer identification
    df = df.rename(columns={
        'fundingRate': 'funding_rate',
        'fundingRateTimestamp': 'timestamp_ms'
    })

    # Converting datatypes
    df['funding_rate'] = df['funding_rate'].astype(float)
    df['timestamp_ms'] = df['timestamp_ms'].astype(int)

    # Creating a more humam-readable timestamp column from the 'timestamp_ms' column
    df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms', utc=True)

    # Sort values on timestamp_ms column from oldest to newest and drop duplicates
    df = df.sort_values('timestamp').drop_duplicates(subset='timestamp_ms')

    df = df[['timestamp', 'timestamp_ms', 'symbol', 'funding_rate']]

    create_data_dir(symbol)
    df.to_csv(get_funding_path(symbol), index=False)

    return len(df)


# ---------------------------------- KLINE (CANDLESTICKS) -------------------------------------
def fetch_klines_page(symbol, category, start_ms, end_ms, interval=60, limit=200):
    """
    This function fetches one page of kline (i.e candlestick) data.
    Returns a list containing the classic OHLCV data.
    """
    url = f"{BASE_URL}/v5/market/kline"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        data = response.json()

        if data['retCode'] != 0:
            log(f"API Error for {symbol} klines: {data['retMsg']}")

        return data['result']['list']

    except Exception as e:
        log(f"Request Error for {symbol} klines: {e}")
        return None


def collect_klines(symbol, category, start_ms=None):
    """
    This function collects all the candlestick history for a particular symbol.
    It saves the results in a csv file and returns the number of records collected.
    """ 
    if start_ms is None:
        start_ms = date_to_ms(
            HISTORY_START_YEAR,
            HISTORY_START_MONTH,
            HISTORY_START_DAY
        )

    end_ms = now_ms()
    all_records = []
    curr_start = start_ms

    # Kline hourly history for the symbol... 200 klines per page
    page_size_ms = 200 * 60 * 60 * 1000

    while curr_start < end_ms:
        curr_end = min(curr_start + page_size_ms, end_ms)

        records = fetch_klines_page(
            symbol, 
            category,
            curr_start,
            curr_end,
        )

        if records is None:
            time.sleep(SLEEP_ON_ERROR)
            curr_start = curr_end + 1
            continue

        if records:
            all_records.extend(records)

        curr_start = curr_end + 1
        time.sleep(SLEEP_BETWEEN_CALLS)

    if not all_records:
        log(f"No {category} kline history data found for {symbol}")
        return 0
    
    df = pd.DataFrame(all_records, columns=[
        'timestamp_ms', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])

     # Convert types
    df['timestamp_ms'] = df['timestamp_ms'].astype(int)
    for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
        df[col] = df[col].astype(float)
    
    # Add human-readable timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms', utc=True)
    
    # Sort and remove duplicate
    df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp_ms'])
    df = df.reset_index(drop=True)
    
    # Keep relevant columns
    df = df[['timestamp', 'timestamp_ms', 'open', 'high', 'low', 'close', 'volume']]
    
    # Save
    create_data_dir(symbol)
    if category == 'linear':
        df.to_csv(get_perp_path(symbol), index=False)
    else:
        df.to_csv(get_spot_path(symbol), index=False)
    
    return len(df)


# -----------------------------------TRACKING PROGRESS--------------------------------
def load_progress():
    """
    This function loads the progress file that tracks which coins are done.
    Therefore, if for some reason, the script crashes, you can resume from where
    you stopped without recollecting coins that have already been collected.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    progress_file = os.path.join(base_dir, 'collection_progress.json')

    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
        
    return {'completed': [], 'failed': []}


def save_progress(progress):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    progress_file = os.path.join(base_dir, 'collection_progress.json')

    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


# ------------------------THE MAIN COLLECTION FUNCTION-------------------------------
progress_lock = threading.Lock()

def collect_single_coin(symbol):
    """
    This function collects all three data types for one coin.
    """
    try:
        time.sleep(random.uniform(0.1, 0.5))
        n_f = collect_funding_rates(symbol)
        n_p = collect_klines(symbol, 'linear')
        n_s = collect_klines(symbol, 'spot')
        total = n_f + n_p + n_s

        if total == 0:
            log(f"WARNING: No data collected for [{symbol}]")
            return(symbol, False, 0) 
        
        log(f"Successfully collected data for [{symbol}]")
        return (symbol, True, total)
    
    except Exception as e:
        log(f"Failure to collect data for [{symbol}]: {e}")
        return(symbol, False, 0) 



def collect_all_historical_data(max_workers=10):
    """
    This is the main function that calls on all the other functions above to
    collect funding rates, perpetual klines, and spot klines for every coin in
    parallel.
    "max_workers" controls simultaneous downloads.
    """
    progress = load_progress()
    completed = set(progress['completed'])
    failed = progress['failed']

    # skip already downloaded coins
    remaining = [c for c in PRODUCT_UNIVERSE if c not in completed]

    log(f"Starting Historical collection...")
    log(f"Total coins: {len(PRODUCT_UNIVERSE)}")
    log(f"Already done: {len(completed)}")
    log(f"Remaining: {len(remaining)}")
    log("=" * 60)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(collect_single_coin, symbol): symbol
            for symbol in remaining
        }

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]

            try:
                symbol, success, records = future.result()

                with progress_lock:
                    if success:
                        completed.add(symbol)
                        progress['completed'] = list(completed)
                        done_count = len(completed)
                        total_count = len(PRODUCT_UNIVERSE)
                        pct = (done_count / total_count) * 100
                        log(f"✅ {symbol} | {records:,} records | "
                            f"{done_count}/{total_count} ({pct:.1f}%)")
                    else:
                        failed.add(symbol)
                        progress['failed'] = list(failed)
                        log(f"❌ {symbol} | FAILED")

                    save_progress(progress)

            except Exception as e:
                log(f"❌ {symbol} | Exception: {e}")

    log("\n" + "=" * 60)
    log(f"Collection complete!")
    log(f"Successful: {len(completed)}")
    log(f"Failed: {len(failed)}")
    if failed:
        log(f"Failed coins: {failed}")


if __name__ == "__main__":
    collect_all_historical_data()
