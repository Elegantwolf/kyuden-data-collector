"""Defaults are anchored to the checkout, never the caller working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "state" / "chrome-profile"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "run" / "collector.lock"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "kyuden.sqlite"
