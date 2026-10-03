"""Optional local HA recorder import at the actual measurement hour.

MQTT state updates cannot rewrite old statistics. A separate external statistic
leaves existing sensor history untouched and supports idempotent backfills.
"""
import asyncio
import json
import logging
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse, urlunparse

from .parsing import JST

logger = logging.getLogger(__name__)


class StatisticsDeliveryError(RuntimeError):
    """Data is persisted but HA statistics synchronization failed."""


@dataclass(frozen=True)
class StatisticsConfig:
    url: str
    token: str = field(repr=False)

    @classmethod
    def from_env(cls):
        url, token = os.getenv("KYUDEN_HA_URL"), os.getenv("KYUDEN_HA_TOKEN")
        if not url and not token:
            return None
        if not url or not token:
            raise ValueError("HA 历史同步需要同时配置 KYUDEN_HA_URL 和 KYUDEN_HA_TOKEN")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
            raise ValueError("HA URL 必须为不含凭据的 http(s) 地址")
        return cls(url, token)

    def websocket_url(self):
        parsed = urlparse(self.url)
        return urlunparse(("wss" if parsed.scheme == "https" else "ws", parsed.netloc,
                           parsed.path.rstrip("/") + "/api/websocket", "", "", ""))


def build_statistics(db_path):
    """Deterministic cumulative sums: replay corrects prior incomplete hours."""
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        rows = conn.execute("SELECT date, hour, usage_kwh FROM hourly_usage ORDER BY date,hour").fetchall()
    if not rows:
        raise ValueError("无小时数据可导入 HA")
    result, cumulative = [], Decimal(0)
    for day, hour, value in rows:
        start = datetime.fromisoformat(day).replace(hour=hour, tzinfo=JST)
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError("小时电量必须是非负有限值")
        if not result:
            result.append({"start": (start - timedelta(hours=1)).astimezone(timezone.utc).isoformat(),
                           "state": 0.0, "sum": 0.0})
        cumulative += amount
        result.append({"start": start.astimezone(timezone.utc).isoformat(),
                       "state": float(cumulative), "sum": float(cumulative)})
    return result


class StatisticsReporter:
    def __init__(self, config):
        self.config = config

    async def publish(self, db_path):
        from websockets.asyncio.client import connect
        stats = await asyncio.to_thread(build_statistics, db_path)
        try:
            async with connect(self.config.websocket_url(), open_timeout=10, close_timeout=5) as ws:
                async def receive():
                    return json.loads(await asyncio.wait_for(ws.recv(), timeout=20))

                if (await receive()).get("type") != "auth_required":
                    raise StatisticsDeliveryError("HA 未请求认证")
                await ws.send(json.dumps({"type": "auth", "access_token": self.config.token}))
                if (await receive()).get("type") != "auth_ok":
                    raise StatisticsDeliveryError("HA 认证失败")
                metadata = {"mean_type": 0, "has_sum": True, "name": "Kyuden Hourly Consumption",
                            "source": "kyuden", "statistic_id": "kyuden:consumption",
                            "unit_class": "energy", "unit_of_measurement": "kWh"}
                # Correcting an old hour also changes every subsequent sum.
                # Recorder upserts by statistic ID and hour, making replay safe.
                for index, offset in enumerate(range(0, len(stats), 500), start=1):
                    await ws.send(json.dumps({"id": index, "type": "recorder/import_statistics",
                                              "metadata": metadata, "stats": stats[offset:offset+500]}))
                    response = await receive()
                    if response.get("id") != index or not response.get("success"):
                        raise StatisticsDeliveryError("HA 拒绝统计导入（需要管理员权限）")
            logger.info("HA 已接受小时历史同步请求: %s 条；recorder 将异步写入", len(stats))
        except Exception as exc:
            # Never include the authentication payload or token in logs.
            raise StatisticsDeliveryError("HA 历史同步失败，SQLite 数据已保留") from exc
