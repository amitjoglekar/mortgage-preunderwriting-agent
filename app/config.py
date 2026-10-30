"""Runtime configuration, read from environment variables (or a .env file)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()
ANTHROPIC_API_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_VERSION = "2023-06-01"

# Force the offline demo extractor even when a key is set (useful for UI testing).
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in {"1", "true", "yes"} or not ANTHROPIC_API_KEY

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
LOANS_DIR = DATA_DIR / "loans"
for d in (UPLOAD_DIR, LOANS_DIR):
    d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
WORKERS = int(os.environ.get("EXTRACTION_WORKERS", "4"))
