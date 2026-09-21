"""Coordinate collection and persistence."""
import os
import logging
from pathlib import Path
from .scraper import KyudenScraper
from .storage import KyudenSQLite

logger = logging.getLogger(__name__)

async def run_collect(
    mode: str,
    hourly_target_date: str | None,
    db_path: str,
    profile_dir: str,
    headless: bool,
    alert_handler=None,
    ha_reporter=None,
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
