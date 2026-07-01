import os
import json
import logging
from dotenv import load_dotenv
from src.config import BASE_DIR
from backend.database.connection import get_connection

load_dotenv()

SUPABASE_DATABASE_URL = os.getenv('DATABASE_URL')
TIMESCALE_DATABASE_URL= os.getenv('TIMESCALE_URL')

SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")


logger  = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TIER_MAP_DB_TO_UI = {
    'large_cap': 'LARGE',
    'mid_cap':   'MID',
    'small_cap': 'SMALL',
    'Unknown':   'SMALL'
}

# Private — mutated in place by load_market_cap_data(), never reassigned
_MARKET_CAP_LOOKUP = {}
_ALL_SYMBOLS       = []



def get_coin_metadata(symbol):
    """
    Returns tier, rank, and display name for a symbol.
    Safe to call from any module — always reads the current in-memory state.
    Falls back to safe defaults if the symbol is not in the lookup.
    """
    return _MARKET_CAP_LOOKUP.get(symbol, {
        'tier': 'SMALL',
        'rank': 9999,
        'name': symbol.replace('USDT', '')
    })


def get_all_symbols():
    """
    Returns the full list of active symbols in order of market cap rank.
    Used by update_data.py to know what to poll each hour.
    """
    return list(_ALL_SYMBOLS)


def get_market_cap_lookup():
    """
    Returns a reference to the full lookup dict.
    Use this only when you need to iterate over all coins —
    prefer get_coin_meta(symbol) for single-symbol lookups.
    """
    return _MARKET_CAP_LOOKUP


def load_market_cap_data():
    """
    Populates the in-memory lookup from coin_universe table.
    Called once at FastAPI startup. All other modules read via
    get_coin_meta() and get_all_symbols() — never import the
    private _MARKET_CAP_LOOKUP or _ALL_SYMBOLS directly.
    """
    _MARKET_CAP_LOOKUP.clear()
    _ALL_SYMBOLS.clear()

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol, name, market_cap_rank, market_cap_tier
                    FROM coin_universe
                    WHERE is_active = true
                    ORDER BY market_cap_rank ASC NULLS LAST
                """)
                rows = cur.fetchall()

        if not rows:
            logger.warning("coin_universe table empty — run get_market_caps.py")
            _fallback_load_from_json()
            return

        for row in rows:
            db_tier = row['market_cap_tier'] or 'Unknown'
            ui_tier = TIER_MAP_DB_TO_UI.get(db_tier, 'SMALL')

            _MARKET_CAP_LOOKUP[row['symbol']] = {
                'tier': ui_tier,
                'rank': row['market_cap_rank'] or 9999,
                'name': row['name'] or row['symbol'].replace('USDT', '')
            }
            _ALL_SYMBOLS.append(row['symbol'])

        logger.info(f"Loaded {len(_MARKET_CAP_LOOKUP)} coins from database")

    except Exception as e:
        logger.error(f"Database load failed: {e} — attempting JSON fallback")
        _fallback_load_from_json()


def _fallback_load_from_json():
    """
    Emergency fallback — reads market_cap_classification.json.
    Stale and not automatically updated. Fix the DB connection
    rather than relying on this in production.
    """
    json_path = os.path.join(BASE_DIR, 'market_cap_classification.json')
    if not os.path.exists(json_path):
        logger.warning("JSON fallback not found — lookup stays empty")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    for tier_key, ui_tier in TIER_MAP_DB_TO_UI.items():
        for coin in data.get(tier_key, []):
            _MARKET_CAP_LOOKUP[coin['symbol']] = {
                'tier': ui_tier,
                'rank': coin.get('rank', 9999),
                'name': coin.get('name', coin['symbol'])
            }

    logger.warning(
        f"Loaded {len(_MARKET_CAP_LOOKUP)} coins from deprecated JSON fallback. "
        f"Run get_market_caps.py to refresh coin_universe table."
    )