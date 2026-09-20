import unittest
from unittest.mock import AsyncMock, patch
from kyuden.service import run_collect
from kyuden.export import save_results


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_dataset_does_not_open_database(self):
        with patch("kyuden.service.KyudenScraper") as scraper, patch("kyuden.service.KyudenSQLite") as db:
            scraper.return_value.scrape = AsyncMock(return_value={})
            with self.assertRaises(ValueError):
                await run_collect("both", None, "unused.sqlite", "unused-profile", True)
            db.assert_not_called()

    def test_disabled_export(self):
        self.assertEqual(save_results(daily=[{}], save_format="none"), {})

    def test_invalid_export_format(self):
        with self.assertRaises(ValueError):
            save_results(save_format="invalid")
