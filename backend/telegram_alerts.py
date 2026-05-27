import os
import logging
import requests
from datetime import datetime, timezone
from database.timescale import get_connection
from database.supabase import get_supabase_connection

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# This is how much rho must increase (relative to the entry level)
# send an intensification alert i.e 50% increase
INTENSIFICATION_THRESHOLD = 0.5


def send_message(chat_id, text):
    """
    This function sends a telegram message to one user
    Returns True if successful, and False if failed.
    """
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
        return False
    
    url  = f"{TELEGRAM_API}/sendMessage"
    data = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url=url, data=data, timeout=10)
        result   = response.json()

        if not result.get('ok'):
            error = result.get('description', 'unknown error')
            logger.warning(f"Telegram send failed for {chat_id}: {error}")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"Telegram request failed: {e}")
        return False
    

def is_quiet_hours():
    """
    This function checks if the current time is between 11pm and 6am UTC
    i.e Quiet hours.
    Returns True if it is, and False if it isnt
    """
    hour = datetime.now(timezone.utc).hour
    return hour >= 23 or hour < 6


def fmt_opportunity_opened(symbol, rho, signal, tier, rank, perp_price,
                           spot_price, premium_pct):
    symbol_display = symbol.replace('USDT', '')
    sign           = '+' if rho > 0 else ''
    is_short       = signal == 'SHORT_PERP_LONG_SPOT'
    signal_line    = "🔴 *SHORT PERP* signal" if is_short else "🔵 *LONG PERP* signal"
    strategy       = (
        "Short the perpetual, buy spot.\nCollect funding every 8 hours."
        if is_short else
        "Long the perpetual, short spot.\nCollect funding every 8 hours."
    )

    return (
        f"⚡ *NEW OPPORTUNITY — {symbol_display}*\n"
        f"\n"
        f"{signal_line}\n"
        f"\n"
        f"*ρ deviation:* `{sign}{rho:.1f}%` annualized\n"
        f"*Tier:* {tier} (#{rank})\n"
        f"*Perp:* `${perp_price:.6f}`\n"
        f"*Spot:* `${spot_price:.6f}`\n"
        f"*Premium:* `{premium_pct:+.4f}%`\n"
        f"\n"
        f"*Strategy:*\n"
        f"{strategy}\n"
        f"\n"
        f"[View on PerpScope](https://perpscope.app/coin/{symbol})"
    )