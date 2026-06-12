import os
import logging
import requests
from datetime import datetime, timezone
from backend.database.connection import get_connection
from src.utils import log_info, log_warn, log_err

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# This is how much rho must increase (relative to the entry level)
# before we can send an intensification alert i.e 50% increase.
INTENSIFICATION_THRESHOLD = 0.5


def send_message(chat_id, text):
    """
    This function sends a telegram message to one user
    Returns True if successful, and False if failed.
    """
    if not TELEGRAM_TOKEN:
        log_warn("TELEGRAM_BOT_TOKEN not set")
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
            log_err(f"Telegram send failed for {chat_id}: {error}")
            return False
        
        return True
    
    except Exception as e:
        log_err(f"Telegram request failed: {e}")
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


def fmt_opportunity_closed(symbol, rho, open_duration_hours, entry_rho, peak_rho):
    display_symbol = symbol.replace('USDT', '')
    hours          = int(open_duration_hours)

    return (
        f"✅ *CLOSED — {display_symbol}*\n"
        f"\n"
        f"ρ has returned to neutral (`{rho:+.1f}%`)\n"
        f"\n"
        f"*Opened at:* `{entry_rho:+.1f}%`\n"
        f"*Peak:*      `{peak_rho:+.1f}%`\n"
        f"*Duration:*  `{hours} hours`\n"
        f"\n"
        f"Consider closing your position if open.\n"
        f"\n"
        f"[View on PerpScope](https://perpscope-frontend.nwosudavid13.workers.dev/coin/{display_symbol})"
    )


def fmt_opportunity_intensified(symbol, rho, previous_rho, entry_rho):
    display_symbol = symbol.replace('USDT', '')
    increase       = ((abs(rho) - abs(previous_rho)) / abs(previous_rho)) * 100
    from_entry     = ((abs(rho) - abs(entry_rho)) / abs(entry_rho)) * 100

    return (
        f"🔥 *INTENSIFIED — {display_symbol}*\n\n"
        f"ρ has jumped significantly\n"
        f"*Entry level:*    `{entry_rho:+.1f}%`\n"
        f"*Previous alert:* `{previous_rho:+.1f}%`\n"
        f"*Current alert:*  `{rho:+.1f}%` (`+{increase:.0f}%` increase from `{from_entry:+.0f}%` from entry)"
        f"\n\n"
        f"May warrant position review.\n\n"
        f"[View on PerpScope](https://perpscope-frontend.nwosudavid13.workers.dev/coin/{display_symbol})"
    )


def get_alerts_states_for_symbol(symbol):
    """
    This function returns all user alert states for one symbol.
    Each row would represent one user who is watching this symbol
    """
    sql = """
        SELECT
            ast.id,
            ast.user_id,
            ast.symbol,
            ast.state,
            ast.opened_at,
            ast.entry_rho,
            ast.last_alert_rho,
            ast.last_alerted_at,
            u.telegram_chat_id,
            ua.threshold_tier,
            ua.min_rho,
            ua.market_cap_tier AS alert_tier_filter
        FROM alert_state    ast
        JOIN users          u       ON ast.user_id = u.id
        JOIN user_alerts    ua      ON ua.user_id  = ast.user_id
                                    AND (ua.symbol = ast.symbol OR ua.symbol IS NULL)
        WHERE ast.symbol = %s
          AND u.telegram_chat_id IS NOT NULL
          AND ua.is_active = true
          AND u.is_active  = true
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (symbol,))
            rows = cur.fetchall

    return [dict(r) for r in rows]


def upsert_alert_state(user_id, symbol, state, opened_at=None,
                       entry_rho=None, last_alert_rho=None):
    """
    This function creates or updates the alert state for one user/
    symbol combination.
    """
    sql = """
        INSERT INTO alert_state
            (user_id, symbol, state, opened_at, entry_rho,
            last_alert_rho, last_alerted_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, symbol) DO UPDATE SET
            state           = EXCLUDED.state,
            opened_at       = COALESCE(EXCLUDED.opened_at, alert_state.opened_at),
            entry_rho       = COALESCE(EXCLUDED.entry_rho, alert_state.entry_rho),
            last_alert_rho  = COALESCE(EXCLUDED.last_alert_rho, alert_state.last_alert_rho)
            last_alerted_at = NOW()
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                user_id, symbol, state,
                opened_at, entry_rho, last_alert_rho
            ))
        conn.commit()


def get_threshold_value(tier):
    """
    This function returns the annualized rho threshold for a given fee tier.
    Matches the values in calculate_rho.py
    """
    thresholds = {
        "no_fee": 0.000,
        "low":    0.532,
        "medium": 1.143,
        "high":   1.794
    }
    return thresholds.get(tier, thresholds['high'])


def get_users_with_global_alerts():
    """
    This function returns users who have set up alerts for ALL coins
    (i.e user_alerts rows where symbol IS NULL)
    """
    sql = """
        SELECT DISTINCT
            u.id        AS user_id,
            u.telegram_chat_id,
            ua.threshold_tier,
            ua.min_rho,
            ua.market_cap_tier  AS alert_tier_filter
        FROM user_alerts  ua
        JOIN users        u  ON ua.user_id = u.id
        WHERE ua.symbol IS NULL
          AND ua.is_active = true
          AND u.is_active  = true
          AND u.telegram_chat_id IS NOT NULL
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    return [dict(r) for r in rows]


# ------------------------- MAIN ALERT ENGINE --------------------------------------
def process_coin_alert(coin):
    """
    This function runs the state machine for one coin.
    It fetches all the users watching this coin, evaluates each one,
    and sends alerts where appropriate.
    """
    symbol          = coin['symbol']
    rho             = coin.get('rho_annual') or coin.get('rho')
    signal          = coin['signal']
    is_neutral      = signal == 'NEUTRAL'

    alerts_sent = 0

    watchers = get_alerts_states_for_symbol(symbol)

    all_coin_watchers = get_users_with_global_alerts()

    all_watchers  = {w['user_id']: w for w in watchers}
    for w in all_coin_watchers:
        if w['user_id'] not in all_watchers:
            all_watchers[w['user_id']] = w

    for user_id, watcher in all_watchers.items():
        chat_id         = watcher.get('telegram_chat_id')
        threshold_tier  = watcher.get('threshold_tier', 'high')
        threshold       = get_threshold_value(threshold_tier)
        current_state   = watcher.get('state', 'NEUTRAL')
        entry_rho       = watcher.get('entry_rho') or 0
        last_alert_rho  = watcher.get('last_alert_rho') or 0
        opened_at       = watcher.get('opened_at')

        if not chat_id:
            continue

        abs_rho  = abs(rho)
        is_above = abs_rho > threshold

        # Check tier filter
        alert_tier_filter = watcher.get('alert_tier_filter')
        if alert_tier_filter and alert_tier_filter != coin['tier']:
            # If user wants alerts for a specific tier and this coin is
            # a different tier, then skip entirely
            continue

        # Check min_rho i.e user's personal rho minimum
        user_min_rho = float(watcher.get('min_rho') or 1.0)
        if abs_rho < user_min_rho:
            # if rho of above the breakeven threshold but below
            # the desired rho value the user wants, then there's
            # no need to send an alert
            if current_state == 'NEUTRAL' and is_above:
                upsert_alert_state(
                    user_id, symbol, 'ACTIVE',
                    opened_at=datetime.now(timezone.utc),
                    entry_rho=rho, last_alert_rho=rho
                )
            continue

        # State: NEUTRAL
        if current_state == 'NEUTRAL':
            if is_above and not is_neutral and not is_quiet_hours():
                # Opportunity just opened - send alert
                msg = fmt_opportunity_opened(
                    symbol, rho * 100, signal,
                    coin['tier'], coin['mc_rank'],
                    coin['perp_price'], coin['spot_price'],
                    coin.get('premium', 0) * 100
                )
                if send_message(chat_id, msg):
                    alerts_sent += 1
                    upsert_alert_state(
                        user_id, symbol, 'ACTIVE',
                        opened_at=datetime.now(timezone.utc),
                        entry_rho=rho, last_alert_rho=rho
                    )

        # State: ACTIVE
        elif current_state == 'ACTIVE':
            if not is_above or is_neutral:
                # Opportunity might be closing - do not send alert yet
                upsert_alert_state(user_id, symbol, 'CLOSING')

            elif abs_rho > abs(last_alert_rho) * (1 + INTENSIFICATION_THRESHOLD):
                # rho has jumped significantly - send intensification alert
                if not is_quiet_hours():
                    msg = fmt_opportunity_intensified(
                        symbol, 
                        rho * 100, 
                        last_alert_rho * 100,
                        entry_rho * 100
                    )
                    if send_message(chat_id, msg):
                        alerts_sent += 1
                        upsert_alert_state(
                            user_id, symbol, 'ACTIVE',
                            last_alert_rho=rho
                        )

        # State: CLOSING
        elif current_state == 'CLOSING':
            if is_above and not is_neutral:
                # Probably a brief dip - upsert back to ACTIVE
                upsert_alert_state(user_id, symbol, 'ACTIVE')

            else:
                # Closing is now confirmed - send alert and return to NEUTRAL
                if not is_quiet_hours() and opened_at:
                    now          = datetime.now(timezone.utc)
                    duration_hrs = (now - opened_at).total_seconds() / 3600

                    msg = fmt_opportunity_closed(
                        symbol, 
                        rho * 100, 
                        duration_hrs,
                        entry_rho * 100,
                        last_alert_rho * 100
                    )
                    if send_message(chat_id, msg):
                        alerts_sent += 1

                upsert_alert_state(user_id, symbol, 'NEUTRAL')

        return alerts_sent


def check_and_send_alerts(opportuinities):
    """
    This function is the main entry point called by run/_price_update() in update_data.py

    It takes the list of current opportunities (all the coins with thier current rho and
    signal) and runs the state machine for each one.
    """ 
    if not TELEGRAM_TOKEN:
        return 0
    
    total_alerts = 0

    for coin in opportuinities:
        try:
            sent = process_coin_alert(coin)
            total_alerts += sent
        except Exception as e:
            log_err(f"Alert processing failed for {coin.get('symbol')}: {e}")
            continue

    if total_alerts > 0:
        log_info(f"Sent {total_alerts} Telegram alerts")

    return total_alerts


if __name__ == "__main__":
    ...