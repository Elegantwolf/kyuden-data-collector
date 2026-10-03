import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from kyuden.cli import main
from kyuden.ha import HomeAssistantReporter, MQTTConfig, MQTTDeliveryError
from kyuden.scraper import KyudenScraper
from kyuden.service import plan_hourly_backfill, run_collect
from kyuden.storage import KyudenSQLite


class BackfillTests(unittest.IsolatedAsyncioTestCase):
    def test_previous_day_is_repaired_until_all_24_hours_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.sqlite"
            with KyudenSQLite(path) as db:
                db.init_schema()
                db.upsert_daily([{"date": "2026-10-02", "usage_kwh": 24}])
                db.upsert_hourly([{"date": "2026-10-02", "hour": h, "usage_kwh": 1} for h in range(22)])
                self.assertIn(date(2026, 10, 2), plan_hourly_backfill(path, "hourly", today=date(2026, 10, 3)))
                db.upsert_hourly([{"date": "2026-10-02", "hour": h, "usage_kwh": 1} for h in (22, 23)])
                self.assertNotIn(date(2026, 10, 2), plan_hourly_backfill(path, "hourly", today=date(2026, 10, 3)))
                db.upsert_daily([{"date": "2026-10-02", "usage_kwh": 25}])
                self.assertIn(date(2026, 10, 2), plan_hourly_backfill(path, "hourly", today=date(2026, 10, 3)))

    async def test_verified_page_date(self):
        scraper = KyudenScraper()
        scraper.page = Mock()
        scraper.page.locator.side_effect = [SimpleNamespace(input_value=AsyncMock(return_value="20261001")),
                                            SimpleNamespace(input_value=AsyncMock(return_value="20261003"))]
        self.assertEqual(await scraper._hourly_page_date(), date(2026, 10, 2))

    async def test_inconsistent_page_date_rejected(self):
        scraper = KyudenScraper()
        scraper.page = Mock()
        scraper.page.locator.side_effect = [SimpleNamespace(input_value=AsyncMock(return_value="20261001")),
                                            SimpleNamespace(input_value=AsyncMock(return_value="20261004"))]
        with self.assertRaises(ValueError):
            await scraper._hourly_page_date()

    async def test_database_survives_failed_mqtt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.sqlite"
            reporter = SimpleNamespace(publish_success=AsyncMock(side_effect=MQTTDeliveryError()))
            with patch("kyuden.service.KyudenScraper") as scraper:
                scraper.return_value.scrape = AsyncMock(return_value={"hourly": [{"date": "2026-10-02", "hour": 23, "usage_kwh": 1}]})
                with self.assertRaises(MQTTDeliveryError):
                    await run_collect("hourly", None, str(path), "profile", True, ha_reporter=reporter)
            with KyudenSQLite(path) as db:
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM hourly_usage").fetchone()[0], 1)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_exhausted_publication_propagates(self):
        reporter = HomeAssistantReporter(MQTTConfig(host="unused"))
        with patch("kyuden.ha.read_energy_snapshot", return_value=SimpleNamespace(today_kwh=1, total_kwh=2, last_collected_at="2026-10-03T00:05:00+09:00")), \
                patch.object(reporter, "_publish_with_retry", new=AsyncMock(side_effect=OSError())):
            with self.assertRaises(MQTTDeliveryError):
                await reporter.publish_success("unused", "hourly", {})

    def test_cli_mqtt_failure_exit_code(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"KYUDEN_LOCK": str(Path(directory)/"lock")}, clear=True), \
                patch("sys.argv", ["collector"]), patch("kyuden.cli.run_collect", new=AsyncMock(side_effect=MQTTDeliveryError())):
            self.assertEqual(main(), 21)

    def test_missing_puback_rejected(self):
        import paho.mqtt.client as mqtt
        reporter = HomeAssistantReporter(MQTTConfig(host="unused"))
        with patch.object(mqtt, "Client") as factory:
            client = factory.return_value
            client.loop_start.side_effect = lambda: client.on_connect(client, None, None, SimpleNamespace(is_failure=False), None)
            client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
            client.publish.return_value.is_published.return_value = False
            with self.assertRaises(MQTTDeliveryError):
                reporter._publish([("topic", "value")])
            client.disconnect.assert_called_once()

