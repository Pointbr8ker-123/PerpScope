# backend/routers/webhooks.py
#
# Telegram bot webhook handler.
# Telegram calls this endpoint when a user sends a message to @PerpScopeBot.
# No polling loop needed — Telegram pushes messages here instantly.
#
# Setup: run src/setup_webhook.py once to register this URL with Telegram.
#
# Endpoints:
#   POST /webhook/telegram  → handles incoming Telegram messages


from fastapi import APIRouter, Request
from src.telegram_alerts import send_message
from src.utils import log_info


router = APIRouter(tags=["webhooks"])

@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram calls this url whenever someone sends a message to the PerpScope bot.
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}
    
    message  = body.get('message', {})
    chat_id  = message.get('chat', {}).get('id')
    text     = message.get('text', '')
    username = message.get('from', {}).get('username', 'unknown')

    if not chat_id:
        return {"ok": True}
    
    if '/start' in text:
        reply_text = (
            f"👋 *Welcome to PerpScope Alerts!*\n\n"
            f"Your Chat ID is:\n"
            f"`{chat_id}`\n\n"
            f"Copy this number and paste it into your "
            f"PerpScope account settings at:\n"
            f"perpscope-frontend.nwosudavid13.workers.dev/account\n\n"
            f"You will then receive real-time alerts when "
            f"funding rate opportunities are detected for "
            f"your watched coins."
        )
        send_message(str(chat_id), reply_text)
        log_info(f"Sent chat_id to @{username} ({chat_id})")

    elif '/stop' in text:
        reply_text = (
            f"🛑 *Alerts paused*\n\n"
            f"You will no longer receive PerpScope alerts.\n"
            f"Send /start to resume."
        )
        send_message(str(chat_id), reply_text)
        log_info(f"Paused alerts for @{username}")

    return {"ok": True}