#!/usr/bin/env python3
"""Despliega cada agente a su app de Heroku con la API de builds.

Se usa cuando el directorio del agente no tiene remoto de Heroku ni credenciales
de git disponibles. Empaqueta el arbol de trabajo (sin basura ni secretos), lo
sube al endpoint de sources y dispara un build. No imprime la API key.

Uso:
    python deploy/scripts/deploy_heroku_build.py --dry-run
    python deploy/scripts/deploy_heroku_build.py
    python deploy/scripts/deploy_heroku_build.py --only historia

Lee los secretos de %USERPROFILE%\\\\.config\\\\taller2\\\\.env.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import http.client
import io
import json
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from update_cloud_secrets import heroku_request, read_env, require  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "deploy" / "agents"

AGENTS = (
    {
        "id": "historia",
        "label": "Historia",
        "dir": AGENTS_DIR / "grupo4-agente-historia",
        "app_var": "HEROKU_APP_HISTORIA",
    },
    {
        "id": "geografia",
        "label": "Geografia",
        "dir": AGENTS_DIR / "grupo4-agente-geografia",
        "app_var": "HEROKU_APP_GEOGRAFIA",
    },
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".langgraph",
    ".langgraph_api",
    ".ipynb_checkpoints",
    "node_modules",
}
EXCLUDED_FILES = {".env", ".env.local", "dev.log"}


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.is_dir():
            continue
        if path.name in EXCLUDED_FILES or path.suffix in {".pyc", ".pyo", ".log"}:
            continue
        yield relative, path


def build_tarball(root: Path) -> tuple[bytes, int, str]:
    """Tarball deterministico (mtime/uid/gid fijos) para que el hash sea estable."""
    buffer = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for relative, path in iter_files(root):
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if path.suffix == ".sh" else 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
            count += 1
    # gzip con mtime=0: el mismo arbol produce siempre el mismo sha256.
    data = gzip.compress(buffer.getvalue(), compresslevel=9, mtime=0)
    return data, count, hashlib.sha256(data).hexdigest()


def put_bytes(url: str, data: bytes, timeout: int = 180) -> int:
    """Sube el tarball sin Content-Type: la URL pre-firmada de S3 no lo incluye."""
    parts = urlsplit(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    connection = http.client.HTTPSConnection(parts.netloc, timeout=timeout)
    try:
        connection.request("PUT", path, body=data)
        response = connection.getresponse()
        payload = response.read(300)
        if response.status not in (200, 201):
            raise SystemExit(f"la subida devolvio HTTP {response.status}: {payload[:200]!r}")
        return response.status
    finally:
        connection.close()


def upload_source(env: dict, app: str, data: bytes) -> str:
    status, payload = heroku_request(env, "POST", f"/apps/{app}/sources")
    if status not in (200, 201, 202) or not isinstance(payload, dict):
        raise SystemExit(f"{app}: POST /sources devolvio HTTP {status}")
    blob = payload.get("source_blob") or {}
    put_url, get_url = blob.get("put_url"), blob.get("get_url")
    if not put_url or not get_url:
        raise SystemExit(f"{app}: /sources no devolvio put_url/get_url")

    put_bytes(put_url, data)
    return get_url


def trigger_build(env: dict, app: str, source_url: str, version: str) -> str:
    status, payload = heroku_request(
        env,
        "POST",
        f"/apps/{app}/builds",
        {"source_blob": {"url": source_url, "version": version}},
    )
    if status not in (200, 201, 202) or not isinstance(payload, dict):
        raise SystemExit(f"{app}: POST /builds devolvio HTTP {status}")
    build_id = payload.get("id")
    if not build_id:
        raise SystemExit(f"{app}: /builds no devolvio id")
    return build_id


def wait_build(env: dict, app: str, build_id: str, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        status, payload = heroku_request(env, "GET", f"/apps/{app}/builds/{build_id}")
        if status != 200 or not isinstance(payload, dict):
            raise SystemExit(f"{app}: GET /builds/{build_id} devolvio HTTP {status}")
        state = payload.get("status") or ""
        if state != last:
            print(f"  build {build_id[:8]}: {state}")
            last = state
        if state == "succeeded":
            return state
        if state in ("failed", "cancelled"):
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:1500])
            raise SystemExit(f"{app}: el build {build_id} termino en {state}")
        time.sleep(6)
    raise SystemExit(f"{app}: el build {build_id} no termino en {timeout}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Despliegue de los agentes a Heroku por API de builds.")
    parser.add_argument("--dry-run", action="store_true", help="Empaquetar y mostrar, sin desplegar.")
    parser.add_argument("--only", choices=[a["id"] for a in AGENTS], help="Desplegar un solo agente.")
    parser.add_argument(
        "--env-file",
        default=str(Path.home() / ".config" / "taller2" / ".env"),
        help="Archivo de secretos (por defecto, fuera del repositorio).",
    )
    parser.add_argument("--timeout", type=int, default=900, help="Segundos de espera por build.")
    args = parser.parse_args()

    env = read_env(Path(args.env_file))
    targets = [a for a in AGENTS if not args.only or a["id"] == args.only]

    prepared = []
    for agent in targets:
        app = require(env, agent["app_var"])
        if not agent["dir"].is_dir():
            raise SystemExit(f"no existe el directorio {agent['dir']}")
        data, count, digest = build_tarball(agent["dir"])
        prepared.append((agent, app, data, count, digest))
        print(f"{agent['label']} ({app}): {count} archivos, {len(data) / 1024:.0f} KiB, sha256={digest[:12]}")

    if args.dry_run:
        print("Dry run: no se desplego nada.")
        return 0

    build_ids = []
    for agent, app, data, _, digest in prepared:
        print(f"{agent['label']} ({app}): subiendo fuente...")
        source_url = upload_source(env, app, data)
        build_id = trigger_build(env, app, source_url, digest[:12])
        print(f"{agent['label']} ({app}): build {build_id} en curso")
        build_ids.append((agent, app, build_id))

    for agent, app, build_id in build_ids:
        print(f"{agent['label']} ({app}): esperando build {build_id}...")
        wait_build(env, app, build_id, args.timeout)

    print("OK: builds terminados. Ejecuta configure_agent_cards.py para verificar las Agent Cards.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"ERROR HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}", file=sys.stderr)
        raise SystemExit(1)
