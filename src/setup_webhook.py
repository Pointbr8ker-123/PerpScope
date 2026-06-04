import requests
import os
from dotenv import load_dotenv
from src.utils import log_info, log_err

load_dotenv()

TOKEN       = os.getenv('TELEGRAM_BOT_TOKEN')
RENDER_URL  = os.getenv('RENDER_URL')
WEBHOOK_URL = f"{RENDER_URL}/webhook/telegram"


def set_webhook():
    url      = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(url, json={"url": WEBHOOK_URL})
    data     = response.json()

    if data.get('ok'):
        log_info("✅ Webhook set successfully")
        log_info(f"URL: {WEBHOOK_URL}")
    else:
        log_err(f"❌ Failed: {data}")


def check_webhook():
    url      = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
    response = requests.get(url)
    data     = response.json()
    log_info(f"Current webhook info:")
    log_info(f"  URL:            {data['result'].get('url')}")
    log_info(f"  Pending updates:{data['result'].get('pending_update_count')}")
    log_err(f"  Last error:     {data['result'].get('last_error_message', 'none')}")

if __name__ == "__main__":
    set_webhook()
    print()
    check_webhook()