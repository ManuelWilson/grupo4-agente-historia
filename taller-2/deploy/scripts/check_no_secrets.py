#!/usr/bin/env python3
"""Escanea el proyecto antes de empaquetar la entrega.

Uso:
    python deploy/scripts/check_no_secrets.py
    python deploy/scripts/check_no_secrets.py ruta/a/revisar

Devuelve codigo 1 si encuentra credenciales, archivos .env o rutas absolutas
de usuario. Nunca imprime el valor completo de un secreto.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
    ".langgraph_api",
    ".langgraph",
    ".ipynb_checkpoints",
    "dist",
    ".vscode",
    ".idea",
}

SKIP_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".zip",
    ".7z",
    ".gz",
    ".tgz",
    ".pyc",
    ".pyo",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp3",
    ".wav",
    ".mp4",
    ".webm",
    ".xlsx",
    ".docx",
}

PLACEHOLDER_VALUES = {
    "",
    "replace-me",
    "replace_with_random_64_hex",
    "replace-with-random-64-hex",
    "changeme",
    "change-me",
    "example",
    "placeholder",
    "dummy",
    "fake",
    "none",
    "null",
    "true",
    "false",
    "tu_clave",
    "tu_token",
    "tu-key",
    "tu-clave",
    "tu-token",
    "your-key",
    "your-token",
    "your-secret",
    "test",
    "redacted",
    "***",
    "[redacted]",
    "...",
    "123456",
    "123456789",
}

PLACEHOLDER_PREFIXES = (
    "replace",
    "your-",
    "your_",
    "tu_",
    "tu-",
    "<",
    "${",
    "$",
    "{{",
    "env.",
    "settings.",
    "self.",
    "os.environ",
    "process.env",
    "getenv",
)

# Nombres que contienen TOKEN pero son un número, no una credencial.
NON_SECRET_NAMES = {
    "MAX_OUTPUT_TOKENS",
    "MAX_INPUT_TOKENS",
    "MAX_TOKENS",
    "MIN_TOKENS",
    "TOKENS_PER_MINUTE",
    "TOKEN_COUNT",
    "TOKENS",
}

ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY|PRIVATE_KEY|CLIENT_SECRET)[A-Z0-9_]*)\b
    \s*[:=]\s*
    ["']?([^"'\s#]+)
    """
)

KNOWN_PATTERNS = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("Google ephemeral key", re.compile(r"AQ\.[A-Za-z0-9_-]{20,}")),
    ("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Heroku API key", re.compile(r"HRKU-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    (
        "Private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
]

WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+")
WINDOWS_PATH_RE_ALT = re.compile(r"[A-Za-z]:/Users/[^/\s\"']+")


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'")
    lowered = normalized.lower()
    if lowered in PLACEHOLDER_VALUES:
        return True
    if lowered.startswith(PLACEHOLDER_PREFIXES):
        return True
    if lowered.endswith(("-me", "_here", "-here", "_example", "-example")):
        return True
    if {"replace", "example", "placeholder", "redacted", "your-"} & set(
        re.split(r"[^a-z]+", lowered)
    ):
        return True
    return False


def redact(value: str) -> str:
    value = value.strip().strip("\"'")
    if len(value) <= 6:
        return "*" * len(value)
    return value[:4] + "..." + "*" * min(8, len(value) - 4)


def within_skipped_dir(path: Path, root: Path) -> bool:
    """Mira la ruta *relativa* a la raíz: `dist/stage/x` no se salta por `dist`."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return any(part in SKIP_DIRS for part in parts)


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if within_skipped_dir(path, root):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def scan_file(path: Path, root: Path, findings: list[tuple[str, str, str]]):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    relative = path.relative_to(root)
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        for label, pattern in KNOWN_PATTERNS:
            match = pattern.search(stripped)
            if match:
                findings.append((str(relative), f"linea {lineno}", f"{label}: {redact(match.group(0))}"))
        is_env_file = path.name == ".env" or path.name.startswith(".env.") or path.suffix == ".env"
        if is_env_file:
            for match in ASSIGNMENT_RE.finditer(stripped):
                key, value = match.group(1), match.group(2)
                if key.upper() in NON_SECRET_NAMES or is_placeholder(value):
                    continue
                findings.append(
                    (str(relative), f"linea {lineno}", f"Asignacion sospechosa {key}: {redact(value)}")
                )
        if "C:\\Users\\" in stripped or "C:/Users/" in stripped:
            match = WINDOWS_PATH_RE.search(stripped) or WINDOWS_PATH_RE_ALT.search(stripped)
            if match:
                findings.append((str(relative), f"linea {lineno}", f"Ruta absoluta de usuario: {match.group(0)}"))


def scan(root: Path) -> list[tuple[str, str, str]]:
    """Devuelve los hallazgos de una carpeta sin imprimir nada."""
    findings: list[tuple[str, str, str]] = []

    for env_file in root.rglob(".env*"):
        if not env_file.is_file():
            continue
        if within_skipped_dir(env_file, root):
            continue
        if env_file.name == ".env.example":
            continue
        if env_file.name == ".env" or env_file.name.startswith(".env."):
            findings.append(
                (str(env_file.relative_to(root)), "archivo", "Archivo .env dentro de la entrega")
            )

    for path in iter_files(root):
        scan_file(path, root, findings)

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Busca secretos y rutas absolutas antes de entregar.")
    parser.add_argument("root", nargs="?", default=None, help="Carpeta a escanear (por defecto, la raiz del proyecto).")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    if not root.exists():
        print(f"ERROR: no existe la ruta {root}", file=sys.stderr)
        return 2

    findings = scan(root)

    if findings:
        print("FALLO: se encontraron posibles secretos o rutas no portables:\n")
        for file, location, message in findings:
            print(f"  - {file} ({location}): {message}")
        print(f"\nTotal: {len(findings)} hallazgo(s). No empaquetar hasta limpiarlos.")
        return 1

    print("OK: no se encontraron secretos, archivos .env ni rutas absolutas de usuario.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
