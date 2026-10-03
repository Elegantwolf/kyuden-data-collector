"""Coordinate collection and persistence."""
import os
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from .parsing import JST
from .scraper import KyudenScraper
from .storage import KyudenSQLite

logger = logging.getLogger(__name__)


def plan_hourly_backfill(db_path, mode, backfill_days=0, today=None):
    """Repair recent gaps and settled corrections; never skip across midnight."""
    today = today or datetime.now(JST).date()
    if not 0 <= backfill_days <= 62:
        raise ValueError("backfill_days 必须在 0..62 之间")
    if backfill_days:
        return [today - timedelta(days=i) for i in range(1, backfill_days + 1)]
    candidates = [today - timedelta(days=i) for i in range(1, 4)]
    if not Path(db_path).exists():
        return candidates[:1]
    with closing(sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)) as conn:
        rows = conn.execute("""SELECT h.date, COUNT(*), SUM(h.usage_kwh), d.usage_kwh
            FROM hourly_usage h LEFT JOIN daily_usage d ON d.date=h.date
            GROUP BY h.date""").fetchall()
    known = {row[0]: row[1:] for row in rows}
    return [d for d in candidates if
            (mode in ("daily", "both") and d == candidates[0]) or
            d.isoformat() not in known or known[d.isoformat()][0] < 24 or
            (known[d.isoformat()][2] is not None and
             abs(known[d.isoformat()][1] - known[d.isoformat()][2]) > 0.051)]


async def run_collect(
    mode: str,
    hourly_target_date: str | None,
    db_path: str,
    profile_dir: str,
    headless: bool,
    alert_handler=None,
    ha_reporter=None,
    backfill_days=0,
    statistics_reporter=None,
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
        hourly_backfill_dates=plan_hourly_backfill(db_path, mode, backfill_days)
        if not hourly_target_date else (),
    )

    expected = ("daily", "hourly") if mode == "both" else (mode,)
    if any(key not in result or not isinstance(result[key], list) for key in expected):
        raise ValueError("采集结果缺少请求的数据集")
    daily_rows = result.get("daily") or []
    hourly_rows = result.get("hourly") or []
    logger.info(f"fetched daily={len(daily_rows)}, hourly={len(hourly_rows)}")

    # 入库（幂等 UPSERT）
    with KyudenSQLite(Path(db_path)) as db:
        db.init_schema()
        n1 = db.upsert_daily(daily_rows) if daily_rows else 0
        n2 = db.upsert_hourly(hourly_rows) if hourly_rows else 0
        logger.info(f"upsert daily={n1}, hourly={n2}")

    if statistics_reporter:
        await statistics_reporter.publish(db_path)
    if ha_reporter:
        await ha_reporter.publish_success(
            db_path,
            mode,
            {"daily": len(daily_rows), "hourly": len(hourly_rows)},
        )


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
