import os
import asyncio
import json
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import logging
from urllib.request import Request, urlopen

from kyuden_scraper import AuthenticationRequiredError, KyudenScraper
from db import KyudenSQLite, DEFAULT_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

AUTH_REQUIRED_EXIT_CODE = 20


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def collector_lock(path: Path, timeout_seconds: float = 180):
    """Prevent multiple jobs from using the same Chrome profile concurrently."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("w") as lock_file:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"等待另一个采集或人工登录进程超时: {path}"
                    ) from exc
                time.sleep(0.25)
        yield


def build_alert_handler(webhook_url: str | None):
    """Build a generic JSON webhook callback; no-op when no URL is configured."""
    if not webhook_url:
        return None

    async def send_alert(message: str, context: dict):
        payload = json.dumps(
            {"message": message, "context": context},
            ensure_ascii=False,
        ).encode("utf-8")

        def post():
            request = Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=10) as response:
                response.read()

        try:
            await asyncio.to_thread(post)
        except Exception as exc:
            logger.error("通知 webhook 调用失败: %s", exc)

    return send_alert

async def run_collect(
    mode: str,
    hourly_target_date: str | None,
    db_path: str,
    profile_dir: str,
    headless: bool,
    alert_handler=None,
):
    scraper = KyudenScraper(
        profile_dir=profile_dir,
        alert_handler=alert_handler,
        browser_channel=os.getenv("KYUDEN_BROWSER_CHANNEL", "chrome"),
    )

    result = await scraper.scrape(
        username=None,
        password=None,
        mode=mode,
        save_format="none",              # 只拿内存数据
        headless=headless,
        hourly_target_date=hourly_target_date,
        profile_dir=profile_dir,
        allow_password_login=False,
    )

    daily_rows = result.get("daily") or []
    hourly_rows = result.get("hourly") or []
    logger.info(f"fetched daily={len(daily_rows)}, hourly={len(hourly_rows)}")

    # 入库（幂等 UPSERT）
    with KyudenSQLite(Path(db_path)) as db:
        db.init_schema()
        n1 = db.upsert_daily(daily_rows) if daily_rows else 0
        n2 = db.upsert_hourly(hourly_rows) if hourly_rows else 0
        logger.info(f"upsert daily={n1}, hourly={n2}")


async def run_interactive_login(
    profile_dir: str,
    timeout_seconds: int,
    alert_handler=None,
) -> bool:
    scraper = KyudenScraper(
        profile_dir=profile_dir,
        alert_handler=alert_handler,
        browser_channel=os.getenv("KYUDEN_BROWSER_CHANNEL", "chrome"),
    )
    return await scraper.interactive_login(timeout_seconds=timeout_seconds)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kyuden collector (scrape + SQLite upsert)")
    parser.add_argument("-m", "--mode", choices=["daily", "hourly", "both"], default="hourly")
    parser.add_argument("--hourly-date", help="小时数据归属日期（YYYY-MM-DD）")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 文件路径")
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("KYUDEN_PROFILE_DIR", "state/chrome-profile"),
        help="专用持久化 Chrome profile 路径",
    )
    parser.add_argument(
        "--interactive-login",
        action="store_true",
        help="打开 Chrome，等待人工完成登录/验证，然后保存 profile",
    )
    parser.add_argument(
        "--auth-timeout",
        type=int,
        default=int(os.getenv("KYUDEN_AUTH_TIMEOUT", "900")),
        help="人工登录等待秒数",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="采集时显示 Chrome 窗口（人工登录始终显示）",
    )
    args = parser.parse_args()

    profile_dir = str(Path(args.profile_dir).expanduser().resolve())
    lock_path = Path(os.getenv("KYUDEN_LOCK", "run/collector.lock")).expanduser().resolve()
    lock_timeout = float(os.getenv("KYUDEN_LOCK_TIMEOUT", "180"))
    alert_handler = build_alert_handler(os.getenv("KYUDEN_NOTIFY_WEBHOOK"))

    try:
        with collector_lock(lock_path, timeout_seconds=lock_timeout):
            if args.interactive_login:
                ok = asyncio.run(
                    run_interactive_login(profile_dir, args.auth_timeout, alert_handler)
                )
                return 0 if ok else 1

            asyncio.run(
                run_collect(
                    args.mode,
                    args.hourly_date,
                    args.db,
                    profile_dir,
                    headless=not args.headed and _env_bool("KYUDEN_HEADLESS", True),
                    alert_handler=alert_handler,
                )
            )
            return 0
    except AuthenticationRequiredError:
        logger.error(
            "登录状态已失效。请运行: python collector.py --interactive-login"
        )
        return AUTH_REQUIRED_EXIT_CODE
    except Exception as exc:
        logger.error("采集失败: %s", exc)
        if alert_handler:
            asyncio.run(
                alert_handler(
                    "采集失败",
                    {"stage": "collector", "exception": type(exc).__name__},
                )
            )
        return 1

if __name__ == "__main__":
    sys.exit(main())
