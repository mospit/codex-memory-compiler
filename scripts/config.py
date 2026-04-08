"""Path constants and time helpers for the personal knowledge base."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Chicago"

ROOT_DIR = Path(os.getenv("KB_ROOT_DIR", Path(__file__).resolve().parent.parent)).resolve()
DAILY_DIR = ROOT_DIR / "daily"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
QA_DIR = KNOWLEDGE_DIR / "qa"
REPORTS_DIR = ROOT_DIR / "reports"
SCRIPTS_DIR = ROOT_DIR / "scripts"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"

INDEX_FILE = KNOWLEDGE_DIR / "index.md"
LOG_FILE = KNOWLEDGE_DIR / "log.md"
STATE_FILE = SCRIPTS_DIR / "state.json"

TIMEZONE = os.getenv("KB_TIMEZONE", DEFAULT_TIMEZONE)


def timezone_info() -> ZoneInfo:
    """Return the configured timezone."""
    return ZoneInfo(TIMEZONE)


def now_dt() -> datetime:
    """Return the current time in the configured timezone.

    Tests can pin the clock with `KB_NOW`.
    """

    override = os.getenv("KB_NOW")
    if override:
        parsed = datetime.fromisoformat(override)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone_info())
        return parsed.astimezone(timezone_info())
    return datetime.now(timezone_info())


def now_iso() -> str:
    """Current time in ISO 8601 format."""
    return now_dt().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date in ISO 8601 format."""
    return now_dt().strftime("%Y-%m-%d")
