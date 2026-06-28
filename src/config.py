import json
import os


# File Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UNIVERSE_FILE = os.path.join(BASE_DIR, 'coin_universe.json')
MARKET_CAP_CLASSIFICATION =  os.path.join(BASE_DIR, 'market_cap_classification.json')


def load_universe():
    """
    This function loads the coins universe created from the get_universe.py file
    """
    if not os.path.exists(UNIVERSE_FILE):
        raise FileNotFoundError(
            "coin_universe.json file not found. "
            "Run get_universe.py file first."
        )
    
    with open(UNIVERSE_FILE, 'r') as f:
        return json.load(f)
    

# Data
coin_universe = load_universe()
RESEARCH_UNIVERSE = coin_universe['research_universe']
PRODUCT_UNIVERSE = coin_universe['product_universe']


# API Settings
BASE_URL = "https://api.bybit.com"
REQUEST_TIMEOUT = 10
SLEEP_BETWEEN_CALLS = 2.0
SLEEP_BETWEEN_COINS = 1.0
SLEEP_ON_ERROR = 10.0

# CoinGecko API
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/coins"


# Data Settings
KLINE_INTERVAL = 60
HISTORY_START_YEAR = 2022
HISTORY_START_MONTH = 1
HISTORY_START_DAY = 1


def create_data_dir(symbol):
    """
    This function creates a folder for a coin if it doesn't exist
    """
    path = os.path.join(DATA_DIR, symbol)
    os.makedirs(path, exist_ok=True)
    return path

def get_funding_path(symbol):
    return os.path.join(DATA_DIR, symbol, f'{symbol}_funding_rates.csv')

def get_perp_path(symbol):
    return os.path.join(DATA_DIR, symbol, f'{symbol}_perp_hourly.csv')

def get_spot_path(symbol):
    return os.path.join(DATA_DIR, symbol, f'{symbol}_spot_hourly.csv')

def get_coin_list():
    """This function would focus on returning a list consisting of large_cap
    and mid_cap coins for now at this MVP level due to database restrictions"""
    with open(MARKET_CAP_CLASSIFICATION, 'r') as f:
        data = json.load(f)

    coin_list = []
    for tier in ('large_cap', 'mid_cap', 'small_cap'):
        for coin in data[tier]:
            coin_list.append(coin['symbol'])

    return coin_list


TIER_LABELS = {
    'large_cap': 'LARGE',
    'mid_cap':   'MID',
    'small_cap': 'SMALL',
}

def get_coin_metadata():
    """
    Returns a dict consisting of metadata for large_cap 
    and mid_cap coins.
    """
    with open(MARKET_CAP_CLASSIFICATION, 'r') as f:
        data = json.load(f)

    coin_metadata = {}
    for tier_key in ('large_cap', 'mid_cap', 'small_cap'):
        tier_label = TIER_LABELS[tier_key]
        for coin in data[tier_key]:
            coin_metadata[coin['symbol']] = {
                'name': coin['name'],
                'tier': tier_label,
                'rank': coin['rank'],
                'market_cap': coin['market_cap'],
                'coingecko_id': coin['coingecko_id'],
            }
    return coin_metadata


ALL_COINS = get_coin_list()
MARKET_CAP_LOOKUP = get_coin_metadata()
