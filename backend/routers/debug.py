# backend/routers/debug.py
#
# Diagnostic endpoints for checking data health at runtime
#
# Routes:
#   GET /debug/lookup           -> Market cap lookup table status
#   GET /debug/prices/{symbol}  -> Latest 5 perp + spot rows for a coin


from fastapi import APIRouter
from backend.database.connection import get_connection
from src.config import ALL_COINS


router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/debug/lookup")
async def debug_lookup():
    return {
        "lookup_size": len(ALL_COINS),
        "sample": dict(list(ALL_COINS.items())[:3]),
        "all_symbols_count": len(ALL_COINS)
    }


@router.get("/debug/prices/{symbol}")
async def debug_prices(symbol):
    symbol = symbol.upper()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT close, timestamp, timestamp_ms
                FROM perp_prices
                WHERE symbol = %s
                ORDER BY timestamp DESC
                LIMIT 5
            """, (symbol,))
            p_rows = cur.fetchall()

            cur.execute("""
                SELECT close, timestamp, timestamp_ms
                FROM spot_prices
                WHERE symbol = %s
                ORDER BY timestamp_ms DESC
                LIMIT 5
            """, (symbol,))
            s_rows = cur.fetchall()

    return {
        "symbol": symbol,
        "latest_perp": [dict(r) for r in p_rows],
        "latest_spot": [dict(r) for r in s_rows]
    }