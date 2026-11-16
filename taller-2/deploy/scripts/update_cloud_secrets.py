#!/usr/bin/env python3
"""Sincroniza secretos nuevos desde el .env seguro hacia Lambda, Heroku y Telegram.

Uso:
    python deploy/scripts/update_cloud_secrets.py --google
    python deploy/scripts/update_cloud_secrets.py --telegram-token
    python deploy/scripts/update_cloud_secrets.py --a2a-token
    python deploy/scripts/update_cloud_secrets.py --google --telegram-token

`--a2a-token` copia `A2A_SHARED_TOKEN` a la Lambda y a las dos apps de Heroku.
El código que valida el token debe estar desplegado antes de activarlo en los
agentes; si no, el bot productivo deja de responder.

El archivo por defecto es %USERPROFILE%\\.config\\taller2\\.env (fuera del repo).
Nunca imprime valores de secretos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PLACEHOLDERS = {"", "replace-me", "tu_clave", "tu_token", "<token>", "<key>"}


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"No existe el archivo de secretos: {path}")
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def require(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if value in PLACEHOLDERS:
        raise SystemExit(f"Falta {key} con un valor real en el archivo de secretos.")
    return value


def lambda_client(env: dict[str, str]):
    import boto3

    session = boto3.session.Session(
        aws_access_key_id=require(env, "AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=require(env, "AWS_SECRET_ACCESS_KEY"),
        region_name=env.get("AWS_REGION", "us-east-1"),
    )
    return session.client("lambda")


def update_lambda(env: dict[str, str], updates: dict[str, str]) -> None:
    lam = lambda_client(env)
    cfg = lam.get_function_configuration(FunctionName="gateway-telegram")
    variables = dict((cfg.get("Environment") or {}).get("Variables", {}))
    variables.update(updates)
    lam.update_function_configuration(FunctionName="gateway-telegram", Environment={"Variables": variables})
    for _ in range(30):
        time.sleep(2)
        cfg = lam.get_function_configuration(FunctionName="gateway-telegram")
        if cfg.get("LastUpdateStatus") == "Successful":
            current = (cfg.get("Environment") or {}).get("Variables", {})
            pending = [key for key, value in updates.items() if current.get(key) != value]
            if pending:
                raise SystemExit(f"Lambda: valores no aplicados en {pending}")
            print("Lambda: actualizada y verificada (" + ", ".join(sorted(updates)) + ").")
            return
        if cfg.get("LastUpdateStatus") == "Failed":
            raise SystemExit("Lambda: la actualizacion fallo.")
    raise SystemExit("Lambda: timeout esperando la actualizacion.")


def heroku_request(env: dict[str, str], method: str, path: str, body: dict | None = None):
    token = require(env, "HEROKU_API_KEY")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.heroku.com" + path,
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.heroku+json; version=3",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return response.status, (json.loads(raw) if raw else None)


def update_heroku_var(env: dict[str, str], key: str, value: str) -> None:
    for var in ("HEROKU_APP_HISTORIA", "HEROKU_APP_GEOGRAFIA"):
        app = require(env, var)
        status, _ = heroku_request(env, "PATCH", f"/apps/{app}/config-vars", {key: value})
        if status not in (200, 201, 202):
            raise SystemExit(f"Heroku {app}: PATCH devolvio HTTP {status}")
        print(f"Heroku {app}: {key} actualizada.")


def update_heroku_google(env: dict[str, str], google_key: str) -> None:
    update_heroku_var(env, "GOOGLE_API_KEY", google_key)


def check_agents(env: dict[str, str]) -> None:
    for key in ("A2A_HISTORIA_URL", "A2A_GEOGRAFIA_URL"):
        url = require(env, key).rstrip("/") + "/ok"
        last = None
        for _ in range(20):
            try:
                with urllib.request.urlopen(url, timeout=15) as response:
                    if response.status == 200:
                        print(f"{key}: /ok 200")
                        break
            except Exception as exc:
                last = exc
            time.sleep(3)
        else:
            raise SystemExit(f"{key}: /ok no respondio 200 ({type(last).__name__})")


def telegram_request(token: str, method: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def update_telegram(env: dict[str, str]) -> None:
    token = require(env, "TELEGRAM_TOKEN")
    secret = require(env, "TELEGRAM_SECRET")
    public_url = require(env, "PUBLIC_URL").rstrip("/")
    webhook_url = public_url + "/telegram"

    result = telegram_request(
        token,
        "setWebhook",
        {"url": webhook_url, "secret_token": secret, "allowed_updates": ["message"]},
    )
    if not result.get("ok"):
        raise SystemExit("Telegram: setWebhook fallo.")
    info = telegram_request(token, "getWebhookInfo")
    data = info.get("result", {})
    print("Telegram: webhook configurado en", data.get("url"))
    print("Telegram: pending_update_count =", data.get("pending_update_count"))
    if data.get("last_error_message"):
        print("Telegram: ultimo error =", data["last_error_message"])


def validate_telegram_token(token: str) -> None:
    try:
        me = telegram_request(token, "getMe")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Telegram: el token nuevo no es valido (HTTP {exc.code}). No se modifico nada.")
    if not me.get("ok"):
        raise SystemExit("Telegram: getMe rechazo el token nuevo. No se modifico nada.")
    print("Telegram: token valido para @%s" % me["result"].get("username"))


def validate_google_key(key: str) -> None:
    url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + key
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status != 200:
                raise SystemExit(f"Google: la key nueva respondio HTTP {response.status}. No se modifico nada.")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Google: la key nueva no es valida (HTTP {exc.code}). No se modifico nada.")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Google: no se pudo validar la key ({exc.reason}). No se modifico nada.")
    print("Google: key nueva valida.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza secretos nuevos a Lambda, Heroku y Telegram.")
    parser.add_argument("--google", action="store_true", help="Actualizar GOOGLE_API_KEY en Lambda y Heroku.")
    parser.add_argument("--telegram-token", action="store_true", help="Actualizar TELEGRAM_TOKEN y setWebhook.")
    parser.add_argument(
        "--a2a-token",
        action="store_true",
        help="Actualizar A2A_SHARED_TOKEN en Lambda y en las dos apps de Heroku.",
    )
    parser.add_argument(
        "--env-file",
        default=str(Path.home() / ".config" / "taller2" / ".env"),
        help="Archivo de secretos (por defecto, fuera del repositorio).",
    )
    args = parser.parse_args()
    if not args.google and not args.telegram_token and not args.a2a_token:
        parser.error("Indica --google, --telegram-token y/o --a2a-token.")

    env = read_env(Path(args.env_file))
    updates: dict[str, str] = {}
    if args.google:
        updates["GOOGLE_API_KEY"] = require(env, "GOOGLE_API_KEY")
        validate_google_key(updates["GOOGLE_API_KEY"])
    if args.telegram_token:
        updates["TELEGRAM_TOKEN"] = require(env, "TELEGRAM_TOKEN")
        validate_telegram_token(updates["TELEGRAM_TOKEN"])
    if args.a2a_token:
        updates["A2A_SHARED_TOKEN"] = require(env, "A2A_SHARED_TOKEN")

    if updates:
        update_lambda(env, updates)
    if args.google:
        update_heroku_google(env, updates["GOOGLE_API_KEY"])
        check_agents(env)
    if args.telegram_token:
        update_telegram(env)
    if args.a2a_token:
        update_heroku_var(env, "A2A_SHARED_TOKEN", updates["A2A_SHARED_TOKEN"])

    print("OK: sincronizacion terminada.")
    print("Siguiente paso: python deploy/scripts/verify_phase0.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"ERROR HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}", file=sys.stderr)
        raise SystemExit(1)
