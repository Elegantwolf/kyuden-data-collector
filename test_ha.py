import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from kyuden.ha import HomeAssistantReporter, MQTTConfig, read_energy_snapshot
from kyuden.storage import KyudenSQLite


class EnergySnapshotTests(unittest.TestCase):
    def test_completed_daily_and_current_hourly_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.sqlite"
            with KyudenSQLite(path) as db:
                db.init_schema()
                db.upsert_daily([
                    {"date": "2026-09-20", "usage_kwh": 5, "timestamp": "2026-09-21T01:05:00+09:00"},
                    {"date": "2026-09-21", "usage_kwh": 99, "timestamp": "2026-09-21T01:05:00+09:00"},
                ])
                db.upsert_hourly([
                    {"date": "2026-09-21", "hour": 0, "usage_kwh": 1.25, "timestamp": "2026-09-21T02:05:00+09:00"},
                    {"date": "2026-09-21", "hour": 1, "usage_kwh": 2.5, "timestamp": "2026-09-21T02:05:00+09:00"},
                ])

            snapshot = read_energy_snapshot(path, today=date(2026, 9, 21))
            self.assertEqual(snapshot.today_kwh, 3.75)
            self.assertEqual(snapshot.total_kwh, 8.75)
            self.assertEqual(snapshot.last_collected_at, "2026-09-21T02:05:00+09:00")


class MQTTReporterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reporter = HomeAssistantReporter(MQTTConfig(host="ha.local"))

    def test_discovery_exposes_energy_dashboard_metadata(self):
        messages = dict(self.reporter.discovery_messages())
        total = messages["homeassistant/sensor/kyuden/total_energy/config"]
        today = messages["homeassistant/sensor/kyuden/today_energy/config"]
        self.assertIn('"device_class": "energy"', total)
        self.assertIn('"state_class": "total"', total)
        self.assertIn('"state_class": "total_increasing"', today)

    def test_discovery_exposes_matterbridge_compatible_energy_sensor(self):
        messages = dict(self.reporter.discovery_messages())
        matter = messages[
            "homeassistant/sensor/kyuden/matter_total_energy/config"
        ]
        self.assertIn('"device_class": "energy"', matter)
        self.assertIn('"state_class": "total_increasing"', matter)
        self.assertIn('"unit_of_measurement": "kWh"', matter)
        self.assertIn('"state_topic": "kyuden/energy/total_kwh"', matter)

    async def test_mqtt_publish_retries_transient_failure(self):
        attempts = []

        def publish(messages):
            attempts.append(messages)
            if len(attempts) < 3:
                raise OSError("temporary outage")

        self.reporter._publish = publish
        with patch("kyuden.ha.asyncio.sleep", return_value=None) as sleep:
            await self.reporter._publish_with_retry([("topic", "value")])

        self.assertEqual(len(attempts), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10])

    async def test_auth_alert_has_dedicated_state(self):
        published = []
        self.reporter._publish = lambda messages: published.extend(messages)
        await self.reporter.send_alert("login", {"status": "auth_required"})
        self.assertIn(("kyuden/health/status", "auth_required"), published)

    def test_disabled_without_host(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(MQTTConfig.from_env())


if __name__ == "__main__":
    unittest.main()
