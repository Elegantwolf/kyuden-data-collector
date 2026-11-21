import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from kyuden.parsing import JST
from kyuden.service import run_collect
from kyuden.export import save_results


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_dataset_does_not_open_database(self):
        with patch("kyuden.service.KyudenScraper") as scraper, patch("kyuden.service.KyudenSQLite") as db:
            scraper.return_value.scrape = AsyncMock(return_value={})
            with self.assertRaises(ValueError):
                await run_collect("both", None, "unused.sqlite", "unused-profile", True)
            db.assert_not_called()

    async def test_missing_yesterday_is_retried_after_cooldown_until_it_arrives(self):
        start = datetime(2026, 11, 21, 1, 5, tzinfo=JST)
        old = {"date": "2026-11-19", "usage_kwh": 7.6}
        yesterday = {"date": "2026-11-20", "usage_kwh": 0}
        hour = {"date": "2026-11-21", "hour": 0, "usage_kwh": 0.1}
        with tempfile.TemporaryDirectory() as directory, \
                patch("kyuden.service.KyudenScraper") as scraper, \
                patch("kyuden.service.datetime", wraps=datetime) as clock:
            path = Path(directory) / "usage.sqlite"
            scrape = scraper.return_value.scrape = AsyncMock(side_effect=[
                {"daily": [old], "hourly": [hour]},
                {"hourly": [hour]},
                {"daily": [], "hourly": [hour]},
                {"hourly": [hour]},
                {"daily": [yesterday], "hourly": [hour]},
                {"hourly": [hour]},
            ])
            reporter = AsyncMock()
            clock.now.return_value = start
            with self.assertRaisesRegex(ValueError, "2026-11-20"):
                await run_collect("daily", None, path, "unused", True, ha_reporter=reporter)
            reporter.publish_success.assert_not_awaited()
            for elapsed in (1, 3, 4, 6, 7):
                clock.now.return_value = start + timedelta(hours=elapsed)
                await run_collect("hourly", None, path, "unused", True, ha_reporter=reporter)
            self.assertEqual(
                [call.kwargs["retry_daily"] for call in scrape.await_args_list],
                [False, False, True, False, True, False],
            )
            self.assertEqual(reporter.publish_success.await_count, 5)

    def test_disabled_export(self):
        self.assertEqual(save_results(daily=[{}], save_format="none"), {})

    def test_invalid_export_format(self):
        with self.assertRaises(ValueError):
            save_results(save_format="invalid")
