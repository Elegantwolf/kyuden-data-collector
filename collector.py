import os
import asyncio
from datetime import date
from pathlib import Path
import logging

from kyuden_scraper import KyudenScraper
from db import KyudenSQLite, DEFAULT_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def run_collect(username: str, password: str, mode: str, hourly_target_date: str | None, db_path: str):
    if not username or not password:
        raise RuntimeError("Missing KYUDEN_USER/KYUDEN_PASS in environment")

    storage_state = os.getenv("KYUDEN_STATE", ".kyuden_storage_state.json")
    scraper = KyudenScraper(storage_state_path=storage_state, max_login_retries=int(os.getenv("KYUDEN_MAX_LOGIN_RETRIES", "2")))

    result = await scraper.scrape(
        username=username,
        password=password,
        mode=mode,
        save_format="none",              # 只拿内存数据
        headless=True,
        hourly_target_date=hourly_target_date,
        storage_state_path=storage_state,
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

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kyuden collector (scrape + SQLite upsert)")
    parser.add_argument("--username", "-u", default=os.getenv("KYUDEN_USER","your_username"))
    parser.add_argument("--password", "-p", default=os.getenv("KYUDEN_PASS","your_password"))
    parser.add_argument("-m", "--mode", choices=["daily", "hourly", "both"], default="hourly")
    parser.add_argument("--hourly-date", help="小时数据归属日期（YYYY-MM-DD）")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 文件路径")
    args = parser.parse_args()

    asyncio.run(run_collect(args.username, args.password, args.mode, args.hourly_date, args.db))

if __name__ == "__main__":
    main()