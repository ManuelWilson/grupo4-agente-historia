#!/usr/bin/env python3
"""Verifica el criterio de aceptacion de la Fase 0.

Uso:
    python deploy/scripts/verify_phase0.py
    python deploy/scripts/verify_phase0.py --sin-red   # solo controles locales

Comprueba:
  - no hay .env dentro de la carpeta del proyecto;
  - el escaneo de secretos no encuentra nada;
  - el ZIP de entrega (si existe) no tiene archivos prohibidos;
  - las credenciales viejas de AWS, Heroku, Telegram y Google ya no funcionan;
  - el gateway acepta el secreto actual y rechaza uno invalido;
  - los dos agentes A2A responden /ok.

Los valores viejos se leen de los backups en %USERPROFILE%\\.config\\taller2\\,
fuera del repositorio. El script nunca imprime un secreto completo.

Codigos de salida: 0 = todo cumple, 1 = hay fallos, 2 = solo quedan pendientes.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_no_secrets  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SECURE_DIR = Path.home() / ".config" / "taller2"
SECURE_ENV = SECURE_DIR / ".env"
ZIP = ROOT / "dist" / "taller2-entrega.zip"
PLACEHOLDERS = {"", "replace-me", "replace_with_random_64_hex", "replace-with-random-64-hex"}

OK = "OK"
FALLO = "FALLO"
PEND = "PENDIENTE"

results: list[tuple[str, str]] = []


def add(status: str, message: str) -> None:
    results.append((status, message))


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def usable(value: str | None) -> bool:
    return bool(value) and value.strip() not in PLACEHOLDERS


def find_old_value(key: str, current: str | None) -> tuple[str | None, Path | None]:
    """Busca en los backups el valor anterior de una credencial."""
    if not SECURE_DIR.exists():
        return None, None
    backups = sorted(
        SECURE_DIR.glob(".env.before-*"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for backup in backups:
        try:
            value = read_env(backup).get(key)
        except OSError:
            continue
        if usable(value) and value != current:
            return value, backup
    return None, None


def http_status(url: str, headers: dict[str, str] | None = None, data: bytes | None = None) -> int:
    request = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception as exc:
        raise RuntimeError(type(exc).__name__) from exc


def check_tree() -> None:
    findings = check_no_secrets.scan(ROOT)
    env_files = [item for item in findings if "Archivo .env" in item[2]]
    if env_files:
        add(FALLO, "Hay archivos .env dentro del proyecto: " + ", ".join(item[0] for item in env_files))
    else:
        add(OK, "No hay archivos .env dentro del proyecto.")
    if findings:
        add(FALLO, f"El escaneo de secretos encontro {len(findings)} hallazgo(s); ejecutar check_no_secrets.py.")
    else:
        add(OK, "El escaneo de secretos no encontro hallazgos.")


def check_zip() -> None:
    if not ZIP.exists():
        add(PEND, "No hay ZIP de entrega; generar con deploy/scripts/package_delivery.ps1.")
        return
    import zipfile

    with zipfile.ZipFile(ZIP) as archive:
        names = archive.namelist()
    bad = [
        name
        for name in names
        if name.endswith("/.env")
        or (".env." in name and not name.endswith(".env.example"))
        or "/.git/" in name
        or "/.venv/" in name
        or "__pycache__" in name
        or name.endswith(".log")
    ]
    if bad:
        add(FALLO, "El ZIP contiene archivos prohibidos: " + ", ".join(bad[:5]))
    else:
        add(OK, f"El ZIP de entrega esta limpio ({len(names)} entradas).")


def check_aws(env: dict[str, str]) -> None:
    old, backup = find_old_value("AWS_ACCESS_KEY_ID", env.get("AWS_ACCESS_KEY_ID"))
    if not old or not backup:
        add(PEND, "Sin key vieja de AWS en los backups; no se pudo verificar.")
        return
    try:
        import boto3
        from botocore.exceptions import ClientError

        old_secret = read_env(backup).get("AWS_SECRET_ACCESS_KEY", "")
        boto3.session.Session(
            aws_access_key_id=old,
            aws_secret_access_key=old_secret,
            region_name=env.get("AWS_REGION", "us-east-1"),
        ).client("sts").get_caller_identity()
        add(FALLO, f"La access key vieja de AWS ({old[-4:]}) todavia funciona.")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "?")
        add(OK, f"La access key vieja de AWS ({old[-4:]}) esta rechazada ({code}).")
    except Exception as exc:
        add(PEND, f"No se pudo verificar la key vieja de AWS ({type(exc).__name__}).")


def check_heroku(env: dict[str, str]) -> None:
    old, _ = find_old_value("HEROKU_API_KEY", env.get("HEROKU_API_KEY"))
    if not old:
        add(PEND, "Sin token viejo de Heroku en los backups; no se pudo verificar.")
        return
    try:
        status = http_status(
            "https://api.heroku.com/account",
            {"Authorization": "Bearer " + old, "Accept": "application/vnd.heroku+json; version=3"},
        )
        if status == 200:
            add(FALLO, "El token viejo de Heroku todavia responde 200.")
        elif status in (401, 403):
            add(OK, f"El token viejo de Heroku esta rechazado (HTTP {status}).")
        else:
            add(PEND, f"El token viejo de Heroku respondio HTTP {status}; revisar manualmente.")
    except Exception as exc:
        add(PEND, f"No se pudo verificar el token viejo de Heroku ({type(exc).__name__}).")


def check_telegram(env: dict[str, str]) -> None:
    old, _ = find_old_value("TELEGRAM_TOKEN", env.get("TELEGRAM_TOKEN"))
    if not old:
        add(PEND, "Rotacion del token del bot pendiente: no hay un token distinto en los backups.")
    else:
        try:
            status = http_status(f"https://api.telegram.org/bot{old}/getMe", data=b"{}")
            if status == 200:
                add(FALLO, "El token viejo del bot todavia funciona: revocarlo en BotFather.")
            elif status in (401, 404):
                add(OK, f"El token viejo del bot esta revocado (HTTP {status}).")
            else:
                add(PEND, f"El token viejo del bot respondio HTTP {status}; revisar manualmente.")
        except Exception as exc:
            add(PEND, f"No se pudo verificar el token viejo del bot ({type(exc).__name__}).")

    secret = env.get("TELEGRAM_SECRET", "")
    public_url = env.get("PUBLIC_URL", "").rstrip("/")
    if not usable(secret) or not public_url:
        add(PEND, "Falta TELEGRAM_SECRET o PUBLIC_URL para probar el webhook.")
        return
    url = public_url + "/telegram"
    body = json.dumps({"message": {"chat": {"id": 1}}}).encode()
    headers = {"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": "invalido"}
    try:
        rejected = http_status(url, headers, body)
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
        accepted = http_status(url, headers, body)
        if rejected == 403 and accepted == 200:
            add(OK, "El gateway rechaza un secreto invalido (403) y acepta el actual (200).")
        else:
            add(FALLO, f"Webhook con secreto invalido={rejected} y actual={accepted}; esperado 403/200.")
    except Exception as exc:
        add(PEND, f"No se pudo probar el webhook ({type(exc).__name__}).")


def check_google(env: dict[str, str]) -> None:
    old, _ = find_old_value("GOOGLE_API_KEY", env.get("GOOGLE_API_KEY"))
    if not old:
        add(PEND, "Rotacion de la Google API key pendiente: no hay una key distinta en los backups.")
        return
    url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + old
    try:
        status = http_status(url)
        if status == 200:
            add(FALLO, "La Google API key vieja todavia es valida: revocarla en AI Studio.")
        elif status in (400, 401, 403):
            add(OK, f"La Google API key vieja esta rechazada (HTTP {status}).")
        else:
            add(PEND, f"La Google API key vieja respondio HTTP {status}; revisar manualmente.")
    except Exception as exc:
        add(PEND, f"No se pudo verificar la Google API key vieja ({type(exc).__name__}).")


def check_agents(env: dict[str, str]) -> None:
    for key, label in (("A2A_HISTORIA_URL", "Historia"), ("A2A_GEOGRAFIA_URL", "Geografia")):
        base = env.get(key, "").rstrip("/")
        if not base:
            add(PEND, f"Falta {key} para probar {label}.")
            continue
        try:
            status = http_status(base + "/ok")
            add(OK if status == 200 else FALLO, f"{label}: /ok devolvio HTTP {status}.")
        except Exception as exc:
            add(FALLO, f"{label}: /ok no respondio ({type(exc).__name__}).")


def main() -> int:
    global SECURE_DIR, SECURE_ENV

    parser = argparse.ArgumentParser(description="Verifica el criterio de aceptacion de la Fase 0.")
    parser.add_argument("--sin-red", action="store_true", help="Omitir los controles que usan internet.")
    parser.add_argument(
        "--secrets-dir",
        default=str(SECURE_DIR),
        help="Carpeta con .env y backups a verificar (por defecto, fuera del repositorio).",
    )
    args = parser.parse_args()

    SECURE_DIR = Path(args.secrets_dir).expanduser().resolve()
    SECURE_ENV = SECURE_DIR / ".env"

    check_tree()
    check_zip()

    if not SECURE_ENV.exists():
        add(PEND, f"No existe el archivo de secretos fuera del proyecto: {SECURE_ENV}")
        env: dict[str, str] = {}
    else:
        env = read_env(SECURE_ENV)

    if args.sin_red:
        add(PEND, "Controles de red omitidos por --sin-red.")
    else:
        check_aws(env)
        check_heroku(env)
        check_telegram(env)
        check_google(env)
        check_agents(env)

    width = max(len(status) for status, _ in results)
    for status, message in results:
        print(f"[{status.ljust(width)}] {message}")

    failures = sum(1 for status, _ in results if status == FALLO)
    pending = sum(1 for status, _ in results if status == PEND)
    passed = len(results) - failures - pending
    print("")
    print(f"Resultado: {passed} OK, {failures} fallo(s), {pending} pendiente(s).")
    if failures:
        print("Fase 0: NO CUMPLE. Corregir los fallos antes de entregar.")
        return 1
    if pending:
        print("Fase 0: INCOMPLETA. Quedan verificaciones o rotaciones pendientes.")
        return 2
    print("Fase 0: CUMPLE. El criterio de aceptacion esta completo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
