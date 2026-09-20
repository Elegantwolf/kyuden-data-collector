import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from collector import collector_lock
from kyuden_scraper import AuthenticationRequiredError, KyudenScraper


class FakePage:
    def __init__(self, url: str):
        self.url = url

    async def goto(self, *_args, **_kwargs):
        return None

    async def wait_for_load_state(self, *_args, **_kwargs):
        return None

    async def wait_for_timeout(self, *_args, **_kwargs):
        return None


class AuthenticationStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_localized_account_url_is_logged_in(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.page = FakePage("https://my.kyuden.co.jp/ja-JP/member/account")

        self.assertTrue(await scraper.is_logged_in())

    async def test_identity_provider_url_is_logged_out(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.page = FakePage("https://id.kyuden.co.jp/login")

        self.assertFalse(await scraper.is_logged_in())

    async def test_scheduled_collection_never_retries_password_login(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.is_logged_in = AsyncMock(return_value=False)
        scraper.login = AsyncMock()
        scraper._notify_alert = AsyncMock()

        with self.assertRaises(AuthenticationRequiredError):
            await scraper.ensure_logged_in(None, None, allow_password_login=False)

        scraper.login.assert_not_awaited()
        scraper._notify_alert.assert_awaited_once()


class CollectorLockTests(unittest.TestCase):
    def test_same_profile_cannot_be_used_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collector.lock"
            with collector_lock(path):
                with self.assertRaises(RuntimeError):
                    with collector_lock(path, timeout_seconds=0):
                        pass


if __name__ == "__main__":
    unittest.main()
