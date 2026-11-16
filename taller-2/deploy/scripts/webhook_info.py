"""Consulta el estado del webhook de Telegram."""
import os
import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

if not TELEGRAM_TOKEN:
    raise SystemExit("Falta TELEGRAM_TOKEN en las variables de entorno.")

with httpx.Client(timeout=15.0) as client:
    resp = client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo")
    print("getWebhookInfo:", resp.status_code)
    print(resp.json())
