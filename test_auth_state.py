import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from collector import collector_lock
from kyuden_scraper import AuthenticationRequiredError, KyudenScraper
from kyuden.scraper import LoginCheckError


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
    def test_uses_official_login_entrypoint(self):
        scraper = KyudenScraper(browser_channel=None)
        self.assertEqual(
            scraper.login_url,
            "https://my.kyuden.co.jp/member/?sKbn=0",
        )

    async def test_localized_account_url_is_logged_in(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.page = FakePage("https://my.kyuden.co.jp/ja-JP/member/account")

        self.assertTrue(await scraper.is_logged_in())

    async def test_identity_provider_url_is_logged_out(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.page = FakePage("https://id.kyuden.co.jp/login")

        self.assertFalse(await scraper.is_logged_in())

    async def test_error_page_does_not_prove_auth_expiry(self):
        scraper = KyudenScraper(browser_channel=None)
        scraper.page = FakePage("https://my.kyuden.co.jp/ja-JP/error")

        from unittest.mock import patch
        with patch("kyuden.scraper.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(LoginCheckError):
                await scraper.is_logged_in()

    async def test_timeout_never_requests_human_login(self):
        from unittest.mock import patch
        scraper = KyudenScraper()
        scraper.page = FakePage("https://id.kyuden.co.jp/login")
        scraper.page.goto = AsyncMock(side_effect=TimeoutError())
        scraper._notify_alert = AsyncMock()
        with patch("kyuden.scraper.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(LoginCheckError):
                await scraper.ensure_logged_in(None, None)
        self.assertEqual(scraper.page.goto.await_count, 2)
        scraper._notify_alert.assert_not_awaited()

    async def test_transient_timeout_recovers_on_second_check(self):
        from unittest.mock import patch
        scraper = KyudenScraper()
        scraper.page = FakePage("https://my.kyuden.co.jp/member/account")
        scraper.page.goto = AsyncMock(side_effect=[TimeoutError(), None])
        with patch("kyuden.scraper.asyncio.sleep", new=AsyncMock()):
            self.assertTrue(await scraper.is_logged_in())

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
