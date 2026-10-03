"""Supported command-line entry point."""
import asyncio
import logging
import os
import sys
from pathlib import Path
from .settings import DEFAULT_DB_PATH, DEFAULT_PROFILE_DIR, DEFAULT_LOCK_PATH
from .locking import collector_lock
from .ha import HomeAssistantReporter, MQTTConfig, MQTTDeliveryError
from .notifications import build_alert_handler, combine_alert_handlers
from .scraper import AuthenticationRequiredError
from .service import run_collect, run_interactive_login
from .statistics import StatisticsConfig, StatisticsReporter, StatisticsDeliveryError

logger = logging.getLogger(__name__)
AUTH_REQUIRED_EXIT_CODE = 20
MQTT_FAILED_EXIT_CODE = 21

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    import argparse
    parser = argparse.ArgumentParser(description="Kyuden collector (scrape + SQLite upsert)")
    parser.add_argument("-m", "--mode", choices=["daily", "hourly", "both"], default="hourly")
    parser.add_argument("--hourly-date", help="真实小时页面目标日期（YYYY-MM-DD，最近 62 天）")
    parser.add_argument("--backfill-days", type=int, default=0, help="额外回填最近 N 个完整日期，0..62")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 文件路径")
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("KYUDEN_PROFILE_DIR", str(DEFAULT_PROFILE_DIR)),
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
    lock_path = Path(os.getenv("KYUDEN_LOCK", str(DEFAULT_LOCK_PATH))).expanduser().resolve()
    lock_timeout = float(os.getenv("KYUDEN_LOCK_TIMEOUT", "180"))
    mqtt_config = MQTTConfig.from_env()
    statistics_config = StatisticsConfig.from_env()
    ha_reporter = HomeAssistantReporter(mqtt_config) if mqtt_config else None
    alert_handler = combine_alert_handlers(
        build_alert_handler(os.getenv("KYUDEN_NOTIFY_WEBHOOK")),
        ha_reporter.send_alert if ha_reporter else None,
    )

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
                    ha_reporter=ha_reporter,
                    backfill_days=args.backfill_days,
                    statistics_reporter=StatisticsReporter(statistics_config) if statistics_config else None,
                )
            )
            return 0
    except AuthenticationRequiredError:
        logger.error(
            "登录状态已失效。请运行: python collector.py --interactive-login"
        )
        return AUTH_REQUIRED_EXIT_CODE
    except MQTTDeliveryError:
        logger.error("数据已入库，但 MQTT 发布失败（退出码 21）；下次运行重发最新状态")
        webhook = build_alert_handler(os.getenv("KYUDEN_NOTIFY_WEBHOOK"))
        if webhook:
            asyncio.run(webhook("MQTT 发布失败，数据已保存", {"stage": "mqtt", "status": "failed"}))
        return MQTT_FAILED_EXIT_CODE
    except StatisticsDeliveryError:
        logger.error("数据已入库，但 HA 历史同步失败（退出码 22）")
        if alert_handler:
            asyncio.run(alert_handler("HA 历史同步失败，数据已保存", {"stage": "ha_statistics", "status": "failed"}))
        return 22
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
