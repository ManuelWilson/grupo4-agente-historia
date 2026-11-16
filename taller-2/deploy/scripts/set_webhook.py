"""Configura el webhook de Telegram para apuntar a la Lambda Function URL."""
import os
import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_SECRET = os.environ.get("TELEGRAM_SECRET", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

if not TELEGRAM_TOKEN:
    raise SystemExit("Falta TELEGRAM_TOKEN en las variables de entorno.")
if not PUBLIC_URL:
    raise SystemExit("Falta PUBLIC_URL (URL de la Lambda Function URL).")

webhook_url = f"{PUBLIC_URL.rstrip('/')}/telegram" if not PUBLIC_URL.endswith("/telegram") else PUBLIC_URL

payload = {
    "url": webhook_url,
    "secret_token": TELEGRAM_SECRET,
    "allowed_updates": ["message"],
}

with httpx.Client(timeout=15.0) as client:
    resp = client.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        json=payload,
    )
    print("setWebhook:", resp.status_code)
    print(resp.json())
