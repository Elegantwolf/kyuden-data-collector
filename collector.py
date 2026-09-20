"""Compatibility entry point for existing schedulers."""
from kyuden.cli import main
from kyuden.locking import collector_lock
from kyuden.notifications import build_alert_handler
from kyuden.service import run_collect, run_interactive_login

if __name__ == "__main__":
    raise SystemExit(main())
