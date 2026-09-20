"""Lifecycle tests; never opens a browser or submits credentials."""
import unittest
from unittest.mock import AsyncMock
from kyuden.scraper import KyudenScraper

class ScraperLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_init_still_cleans_up(self):
        scraper = KyudenScraper()
        scraper.init_browser = AsyncMock(side_effect=RuntimeError("test"))
        scraper.close = AsyncMock()
        with self.assertRaises(RuntimeError):
            await scraper.scrape(save_format="none")
        scraper.close.assert_awaited_once()

    async def test_failed_fetch_is_not_success(self):
        scraper = KyudenScraper()
        scraper.init_browser = AsyncMock()
        scraper.ensure_logged_in = AsyncMock(return_value=True)
        scraper.get_daily_usage_data = AsyncMock(side_effect=ValueError("invalid chart"))
        scraper.close = AsyncMock()
        with self.assertRaises(ValueError):
            await scraper.scrape(save_format="none")
        scraper.close.assert_awaited_once()

    async def test_historical_hourly_date_rejected_before_browser(self):
        scraper = KyudenScraper()
        scraper.init_browser = AsyncMock()
        with self.assertRaises(ValueError):
            await scraper.scrape(mode="hourly", hourly_target_date="2000-01-01")
        scraper.init_browser.assert_not_awaited()

if __name__ == "__main__":
    unittest.main()
