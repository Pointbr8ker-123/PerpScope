import json
import os


# File Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UNIVERSE_FILE = os.path.join(BASE_DIR, 'coin_universe.json')


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
BASE_URL = "https://api.bytick.com"
REQUEST_TIMEOUT = 10
SLEEP_BETWEEN_CALLS = 2.0
SLEEP_BETWEEN_COINS = 1.0
SLEEP_ON_ERROR = 10.0


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
