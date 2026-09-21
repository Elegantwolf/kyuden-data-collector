"""Optional local MQTT bridge for Home Assistant."""
import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class EnergySnapshot:
    today_kwh: float
    total_kwh: float
    last_collected_at: str


def read_energy_snapshot(db_path: str | Path, today=None) -> EnergySnapshot:
    """Build HA values without double-counting daily and hourly rows."""
    day = (today or datetime.now(JST).date()).isoformat()
    connection = sqlite3.connect(str(db_path))
    try:
        hourly_today = connection.execute(
            "SELECT COALESCE(SUM(usage_kwh), 0) FROM hourly_usage WHERE date = ?",
            (day,),
        ).fetchone()[0]
        daily_today = connection.execute(
            "SELECT usage_kwh FROM daily_usage WHERE date = ?", (day,)
        ).fetchone()
        today_kwh = float(hourly_today or (daily_today[0] if daily_today else 0))
        completed_days = connection.execute(
            "SELECT COALESCE(SUM(usage_kwh), 0) FROM daily_usage WHERE date < ?",
            (day,),
        ).fetchone()[0]
        last_collected = connection.execute(
            """
            SELECT MAX(fetched_at) FROM (
                SELECT fetched_at FROM daily_usage
                UNION ALL
                SELECT fetched_at FROM hourly_usage
            )
            """
        ).fetchone()[0]
    finally:
        connection.close()
    if not last_collected:
        raise ValueError("数据库还没有可发布的采集记录")
    return EnergySnapshot(
        today_kwh=round(today_kwh, 3),
        total_kwh=round(float(completed_days) + today_kwh, 3),
        last_collected_at=str(last_collected),
    )


@dataclass(frozen=True)
class MQTTConfig:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    base_topic: str = "kyuden"
    discovery_prefix: str = "homeassistant"
    tls: bool = False

    @classmethod
    def from_env(cls):
        host = os.getenv("KYUDEN_MQTT_HOST")
        if not host:
            return None
        return cls(
            host=host,
            port=int(os.getenv("KYUDEN_MQTT_PORT", "1883")),
            username=os.getenv("KYUDEN_MQTT_USERNAME"),
            password=os.getenv("KYUDEN_MQTT_PASSWORD"),
            base_topic=os.getenv("KYUDEN_MQTT_BASE_TOPIC", "kyuden").strip("/"),
            discovery_prefix=os.getenv(
                "KYUDEN_MQTT_DISCOVERY_PREFIX", "homeassistant"
            ).strip("/"),
            tls=os.getenv("KYUDEN_MQTT_TLS", "false").lower()
            in {"1", "true", "yes", "on"},
        )


class HomeAssistantReporter:
    def __init__(self, config: MQTTConfig):
        self.config = config

    def _topic(self, suffix: str) -> str:
        return f"{self.config.base_topic}/{suffix}"

    def discovery_messages(self):
        device = {
            "identifiers": ["kyuden_data_collector"],
            "name": "Kyuden Data Collector",
            "manufacturer": "Kyushu Electric Power",
            "model": "Local collector",
        }
        definitions = {
            "today_energy": {
                "name": "Today Energy",
                "state_topic": self._topic("energy/today_kwh"),
                "unique_id": "kyuden_today_energy",
                "device_class": "energy",
                "state_class": "total_increasing",
                "unit_of_measurement": "kWh",
                "device": device,
            },
            "total_energy": {
                "name": "Total Energy",
                "state_topic": self._topic("energy/total_kwh"),
                "unique_id": "kyuden_total_energy",
                "device_class": "energy",
                "state_class": "total",
                "unit_of_measurement": "kWh",
                "device": device,
            },
            "last_collected": {
                "name": "Last Collected",
                "state_topic": self._topic("health/last_collected"),
                "unique_id": "kyuden_last_collected",
                "device_class": "timestamp",
                "device": device,
            },
            "status": {
                "name": "Collector Status",
                "state_topic": self._topic("health/status"),
                "json_attributes_topic": self._topic("health/details"),
                "unique_id": "kyuden_collector_status",
                "icon": "mdi:transmission-tower",
                "device": device,
            },
        }
        return [
            (
                f"{self.config.discovery_prefix}/sensor/kyuden/{key}/config",
                json.dumps(value, ensure_ascii=False),
            )
            for key, value in definitions.items()
        ]

    def _publish(self, messages):
        import paho.mqtt.client as mqtt

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="kyuden-data-collector",
        )
        if self.config.username:
            client.username_pw_set(self.config.username, self.config.password)
        if self.config.tls:
            client.tls_set()
        client.connect(self.config.host, self.config.port, keepalive=20)
        client.loop_start()
        try:
            for topic, payload in messages:
                info = client.publish(topic, payload, qos=1, retain=True)
                info.wait_for_publish(timeout=10)
        finally:
            client.disconnect()
            client.loop_stop()

    async def publish_success(self, db_path, mode: str, counts: dict):
        try:
            snapshot = read_energy_snapshot(db_path)
            details = {
                "event": "collection_succeeded",
                "mode": mode,
                "daily_rows": counts.get("daily", 0),
                "hourly_rows": counts.get("hourly", 0),
                "at": snapshot.last_collected_at,
            }
            messages = self.discovery_messages() + [
                (self._topic("energy/today_kwh"), str(snapshot.today_kwh)),
                (self._topic("energy/total_kwh"), str(snapshot.total_kwh)),
                (self._topic("health/last_collected"), snapshot.last_collected_at),
                (self._topic("health/status"), "ok"),
                (self._topic("health/details"), json.dumps(details)),
            ]
            await asyncio.to_thread(self._publish, messages)
            logger.info("Home Assistant MQTT 状态发布成功")
        except Exception as exc:
            logger.error("Home Assistant MQTT 发布失败: %s", exc)

    async def send_alert(self, message: str, context: dict):
        status = "auth_required" if context.get("status") == "auth_required" else "failed"
        details = {
            "event": status,
            "message": message,
            "context": context,
            "at": datetime.now(JST).isoformat(),
        }
        try:
            await asyncio.to_thread(
                self._publish,
                self.discovery_messages() + [
                    (self._topic("health/status"), status),
                    (self._topic("health/details"), json.dumps(details, ensure_ascii=False)),
                ],
            )
        except Exception as exc:
            logger.error("Home Assistant MQTT 告警发布失败: %s", exc)
