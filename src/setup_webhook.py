import requests
import os
from dotenv import load_dotenv
from utils import log

load_dotenv()

TOKEN       = os.getenv('TELEGRAM_BOT_TOKEN')
RENDER_URL  = os.getenv('RENDER_URL')
WEBHOOK_URL = f"{RENDER_URL}/webhook/telegram"


def set_webhook():
    url      = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(url, json={"url": WEBHOOK_URL})
    data     = response.json()

    if data.get('ok'):
        log("✅ Webhook set successfully")
        log(f"URL: {WEBHOOK_URL}")
    else:
        log(f"❌ Failed: {data}")


def check_webhook():
    url      = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
    response = requests.get(url)
    data     = response.json()
    log(f"Current webhook info:")
    log(f"  URL:            {data['result'].get('url')}")
    log(f"  Pending updates:{data['result'].get('pending_update_count')}")
    log(f"  Last error:     {data['result'].get('last_error_message', 'none')}")

if __name__ == "__main__":
    set_webhook()
    print()
    check_webhook()