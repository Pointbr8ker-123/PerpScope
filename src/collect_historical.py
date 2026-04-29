import requests
import pandas as pd
import os
import time
import json
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    BASE_URL, RESEARCH_UNIVERSE, PRODUCT_UNIVERSE, REQUEST_TIMEOUT,
    SLEEP_BETWEEN_CALLS, SLEEP_BETWEEN_COINS, SLEEP_ON_ERROR,
    KLINE_INTERVAL, HISTORY_START_DAY, HISTORY_START_MONTH,
    HISTORY_START_YEAR, LARGE_CAP_COINS, create_data_dir,
    get_funding_path, get_perp_path, get_spot_path
)
from utils import date_to_ms, now_ms, log


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
    
    


