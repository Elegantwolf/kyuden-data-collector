# main module for Kyuden electricity usage scraper
import asyncio
import json
import html
import random
from datetime import datetime, date
from playwright.async_api import async_playwright
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, Any, Union
from urllib.parse import urlparse
from .parsing import JST, parse_daily, parse_hourly
from .export import save_dataset, save_results

# 设置日志

logger = logging.getLogger(__name__)


class AuthenticationRequiredError(RuntimeError):
    """The persisted browser profile must be authenticated by a human."""

class KyudenScraper:
    def __init__(
        self,
        storage_state_path: Optional[Union[str, Path]] = None,
        profile_dir: Optional[Union[str, Path]] = None,
        browser_channel: Optional[str] = "chrome",
        alert_handler: Optional[Callable[[str, Dict[str, Any]], Union[None, Awaitable[None]]]] = None,
        max_login_retries: int = 2,
    ):
        self.base_url = "https://my.kyuden.co.jp"
        self.login_url = f"{self.base_url}/member"  # 登录页面更精确
        self.account_url = f"{self.base_url}/ja-JP/member/account"
        self.chart_url = f"{self.base_url}/member/chart_days_current"
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._headless = True
        self._persistent_context = False

        # 新增：登录状态复用与告警配置
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.profile_dir = Path(profile_dir) if profile_dir else None
        self.browser_channel = browser_channel
        self.alert_handler = alert_handler
        self.max_login_retries = max(1, max_login_retries)

    async def _random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """随机延迟，模拟真实用户操作节奏"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def _simulate_human_typing(self, element, text: str):
        """模拟人类输入：先清空输入框，再逐字输入+随机延迟"""
        await element.click()
        await self._random_delay(0.1, 0.3)

        # 先清空输入框（模拟 Ctrl+A 或 Cmd+A 然后删除）
        await element.click(click_count=3)  # 三击全选文本
        await self._random_delay(0.1, 0.2)
        await element.press('Backspace')  # 删除选中内容
        await self._random_delay(0.2, 0.4)

        # 逐字输入
        for char in text:
            await element.type(char, delay=random.uniform(50, 150))
        await self._random_delay(0.3, 0.8)

    async def _simulate_mouse_movement(self):
        """模拟鼠标随机移动"""
        try:
            viewport_size = self.page.viewport_size
            if viewport_size:
                x = random.randint(100, viewport_size['width'] - 100)
                y = random.randint(100, viewport_size['height'] - 100)
                await self.page.mouse.move(x, y)
                await self._random_delay(0.2, 0.5)
        except Exception as e:
            logger.debug(f"鼠标移动模拟失败: {e}")

    async def init_browser(self, headless=True, use_storage_state: bool = True):
        """初始化浏览器。

        优先使用独立的持久化 Chrome profile。它保存完整浏览器会话，比只复制
        cookies/localStorage 的 storage state 更适合需要长期可信会话的网站。
        """
        self._playwright = await async_playwright().start()
        self._headless = headless

        common_options = {
            "headless": headless,
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
        }

        if self.profile_dir:
            self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            launch_options = dict(common_options)
            if self.browser_channel:
                launch_options["channel"] = self.browser_channel
            self.context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                **launch_options,
            )
            self.browser = self.context.browser
            self._persistent_context = True
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            logger.info(
                "持久化浏览器初始化完成 (headless=%s, profile=%s, channel=%s)",
                headless,
                self.profile_dir,
                self.browser_channel or "chromium",
            )
            return

        storage_state = None
        if use_storage_state and self.storage_state_path and self.storage_state_path.exists():
            storage_state = str(self.storage_state_path)
            logger.info(f"加载登录状态: {self.storage_state_path}")

        launch_options = {"headless": headless}
        if self.browser_channel:
            launch_options["channel"] = self.browser_channel
        self.browser = await self._playwright.chromium.launch(**launch_options)

        self.context = await self.browser.new_context(
            storage_state=storage_state,
            locale=common_options["locale"],
            timezone_id=common_options["timezone_id"],
        )
        self.page = await self.context.new_page()
        logger.info(f"浏览器初始化完成 (headless={headless}, use_storage_state={bool(storage_state)})")

    async def _notify_alert(self, message: str, context: Optional[Dict[str, Any]] = None):
        """触发外部报警回调（如有）"""
        logger.error(message)
        if self.alert_handler:
            try:
                res = self.alert_handler(message, context or {})
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"报警回调执行失败: {e}")

    async def is_logged_in(self) -> bool:
        try:
            await self.page.goto(
                self.account_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            # The account URL is briefly visible before the site's client-side
            # authentication redirect. Checking it immediately creates a false
            # positive and closes the manual-login window before login begins.
            await self.page.wait_for_timeout(2500)
            parsed = urlparse(self.page.url)
            logger.info("登录状态检查落点: %s%s", parsed.hostname, parsed.path)
            if parsed.hostname == "id.kyuden.co.jp":
                return False
            return parsed.hostname == "my.kyuden.co.jp" and parsed.path.endswith("/member/account")
        except Exception as e:
            logger.warning(f"登录状态检查异常: {e}")
            return False

    async def interactive_login(self, timeout_seconds: int = 900) -> bool:
        """打开可见 Chrome，等待用户完成登录或验证。"""
        if not self.profile_dir:
            raise ValueError("人工登录必须配置 profile_dir")

        try:
            await self.init_browser(headless=False, use_storage_state=False)
            await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=30000)
            if await self.is_logged_in():
                logger.info("持久化 profile 已处于登录状态")
                return True

            await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=30000)
            logger.info("请在打开的 Chrome 中完成人工登录；最多等待 %s 秒", timeout_seconds)
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            while asyncio.get_running_loop().time() < deadline:
                parsed = urlparse(self.page.url)
                if parsed.hostname == "my.kyuden.co.jp" and parsed.path.endswith("/member/account"):
                    if await self.is_logged_in():
                        logger.info("人工登录成功，Chrome profile 已自动保存")
                        return True
                await asyncio.sleep(2)

            await self._notify_alert("人工登录等待超时", {"stage": "interactive_login"})
            return False
        finally:
            await self.close()

    async def login(self, username, password):
        """执行一次显式登录，并在成功后保存 storage state"""
        try:
            logger.info("开始登录...")
            await self.page.goto(self.login_url)
            await self.page.wait_for_load_state('domcontentloaded')

            # 随机等待，模拟用户阅读页面
            await self._random_delay(2, 4)

            # 模拟鼠标移动
            await self._simulate_mouse_movement()

            email_input = await self.page.query_selector(
                '#email, input[name="email"], input[name="body_1$TxtKaiinId"]'
            )
            if not email_input:
                logger.error("未找到邮箱输入框")
                await self.page.screenshot(path='email_input_not_found.png')
                return False

            # 模拟人类输入
            await self._simulate_human_typing(email_input, username)

            # 随机延迟
            await self._random_delay(0.5, 1.5)

            # 再次模拟鼠标移动
            await self._simulate_mouse_movement()

            password_input = await self.page.query_selector(
                '#password, input[name="password"], input[name="body_1$TxtPasswd"]'
            )
            if not password_input:
                logger.error("未找到密码输入框")
                await self.page.screenshot(path='password_input_not_found.png')
                return False

            # 模拟人类输入密码
            await self._simulate_human_typing(password_input, password)

            # 登录前随机等待
            await self._random_delay(1, 2)

            remember_me = await self.page.query_selector('#remember_me, input[name="remember_me"]')
            if remember_me and not await remember_me.is_checked():
                await remember_me.evaluate("element => element.click()")

            submit_button = await self.page.query_selector(
                '#login_button, button[type="submit"], button.fs-submit'
            )
            if not submit_button:
                logger.error("未找到登录提交按钮")
                await self.page.screenshot(path='submit_button_not_found.png')
                return False

            # 模拟鼠标移动到按钮
            box = await submit_button.bounding_box()
            if box:
                await self.page.mouse.move(
                    box['x'] + box['width'] / 2,
                    box['y'] + box['height'] / 2
                )
                await self._random_delay(0.3, 0.8)

            await submit_button.click()

            try:
                await self.page.wait_for_url('**/member/**', timeout=15000)
            except Exception:
                # 有时不会稳定跳转，尽量容错
                await asyncio.sleep(1)

            # 登录后等待，模拟用户查看页面
            await self._random_delay(2, 4)

            # 登录后再做一次 dashboard 检查
            if not await self.is_logged_in():
                await self.page.screenshot(path='login_failed.png')
                logger.error("登录后未检测到登录态")
                return False

            # 登录成功，保存 storage state
            if self.storage_state_path:
                await self.context.storage_state(path=str(self.storage_state_path))
                logger.info(f"登录状态已保存: {self.storage_state_path}")

            logger.info("登录成功")
            return True
        except Exception as e:
            logger.error(f"登录失败: {e}")
            await self.page.screenshot(path='login_exception.png')
            return False

    async def ensure_logged_in(
        self,
        username: Optional[str],
        password: Optional[str],
        allow_password_login: bool = False,
    ) -> bool:
        """先尝试复用 storage state；失败则退回重登，支持最大重试次数"""
        # 1) 尝试复用状态
        if await self.is_logged_in():
            logger.info("检测到已登录（复用状态）")
            return True

        if not allow_password_login:
            await self._notify_alert(
                "登录状态已失效，需要人工登录",
                {"stage": "login", "status": "auth_required"},
            )
            raise AuthenticationRequiredError("登录状态已失效，需要人工登录")

        if not username or not password:
            raise AuthenticationRequiredError("未提供凭据，需要人工登录")

        # 2) 回退显式登录 + 重试
        for attempt in range(1, self.max_login_retries + 1):
            logger.info(f"尝试显式登录（第 {attempt}/{self.max_login_retries} 次）")
            if await self.login(username, password):
                return True

            if attempt == 1 and self.storage_state_path and not self.profile_dir:
                logger.warning("使用 storage state 登录失败，回退到无状态登录并刷新 storage_state.json")
                try:
                    if self.storage_state_path.exists():
                        self.storage_state_path.unlink()
                        logger.info(f"已删除失效的 storage state: {self.storage_state_path}")
                except Exception as remove_err:
                    logger.warning(f"删除 storage state 失败: {remove_err}")
                await self.close()
                await self.init_browser(headless=self._headless, use_storage_state=False)

            # 增加重试间隔，避免频繁请求
            await asyncio.sleep(min(5 * attempt, 15))

        await self._notify_alert("登录失败，达到最大重试次数", {"stage": "login"})
        return False

    async def get_daily_usage_data(self):
        """获取每日用电量数据"""
        await self._random_delay(1, 2)  # 随机等待
        await self.page.goto(self.account_url, timeout=10000)
        await self._random_delay(1, 2)  # 模拟用户查看页面
        await self.page.click('button.fs-top_card__detail_button.-daily')
        await self.page.wait_for_load_state('domcontentloaded')
        await self._random_delay(1, 3)  # 等待数据加载
        logger.info("导航到每日图表页面完成")
        try:
            data_element = await self.page.query_selector('input[name="body_0$Data"]')
            if not data_element:
                raise Exception("未找到数据元素")
            data_value = await data_element.get_attribute('value')
            if not data_value:
                raise Exception("数据为空")
            usage_data = json.loads(html.unescape(data_value))
            logger.info("成功获取每日数据")
            return self.parse_usage_data(usage_data)
        except Exception as e:
            logger.error(f"获取每日数据失败: {e}")
            raise

    async def get_hourly_usage_data(self, target_date: Optional[date] = None):
        """获取每小时用电量数据（允许传入目标日期归属）"""
        await self.page.wait_for_load_state('networkidle')
        await self._random_delay(1, 2)  # 随机等待
        await self.page.goto(self.account_url, timeout=10000)
        await self._random_delay(1, 2)  # 模拟用户查看页面
        await self.page.click('button.fs-top_card__detail_button.-hourly')
        await self.page.wait_for_load_state('domcontentloaded')
        await self._random_delay(1, 3)  # 等待数据加载
        logger.info("导航到每小时图表页面完成")
        try:
            data_element = await self.page.query_selector('input[name="body_0$Data"]')
            if not data_element:
                raise Exception("未找到数据元素")
            data_value = await data_element.get_attribute('value')
            if not data_value:
                raise Exception("数据为空")
            usage_data = json.loads(html.unescape(data_value))
            logger.info("成功获取每小时原始数据")
            return self.parse_hourly_usage_data(usage_data, target_date=target_date)
        except Exception as e:
            logger.error(f"获取每小时用电量数据失败: {e}")
            raise

    parse_usage_data = staticmethod(parse_daily)
    parse_hourly_usage_data = staticmethod(parse_hourly)

    _save_dataset = staticmethod(save_dataset)
    save = staticmethod(save_results)

    async def close(self):
        if self._persistent_context and self.context:
            await self.context.close()
            self.context = None
            self.browser = None
            self._persistent_context = False
            logger.info("持久化浏览器已关闭")
        elif self.browser:
            await self.browser.close()
            self.browser = None
            logger.info("浏览器已关闭")
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Playwright 已停止")

    async def scrape(
        self,
        username=None,
        password=None,
        mode='daily',
        save_format='both',
        headless=True,
        hourly_target_date: Optional[Union[str, date]] = None,
        storage_state_path: Optional[Union[str, Path]] = None,
        profile_dir: Optional[Union[str, Path]] = None,
        allow_password_login: bool = False,
        max_login_retries: Optional[int] = None,
        alert_handler: Optional[Callable[[str, Dict[str, Any]], Union[None, Awaitable[None]]]] = None,
    ):
        """
        完整爬取流程
        mode: 'daily' | 'hourly' | 'both'
        hourly_target_date: 仅允许日本时区当天，不提供历史页面导航
        """
        if mode not in ('daily', 'hourly', 'both'):
            raise ValueError("未知采集模式")
        # 允许在 scrape 级别覆盖构造参数
        if storage_state_path is not None:
            self.storage_state_path = Path(storage_state_path)
        if profile_dir is not None:
            self.profile_dir = Path(profile_dir)
        if max_login_retries is not None:
            self.max_login_retries = max(1, int(max_login_retries))
        if alert_handler is not None:
            self.alert_handler = alert_handler

        # 解析 hourly 的 target_date
        target_date_obj: Optional[date] = None
        if isinstance(hourly_target_date, str) and hourly_target_date:
            target_date_obj = date.fromisoformat(hourly_target_date)
        elif isinstance(hourly_target_date, date):
            target_date_obj = hourly_target_date

        if target_date_obj and target_date_obj != datetime.now(JST).date():
            raise ValueError("当前小时采集不支持历史日期；不能将当前图表改标为其他日期")

        try:
            await self.init_browser(headless=headless, use_storage_state=True)
            if not await self.ensure_logged_in(
                username,
                password,
                allow_password_login=allow_password_login,
            ):
                logger.error("登录失败，终止")
                raise AuthenticationRequiredError("需要人工登录")

            daily_data = hourly_data = None
            if mode in ('daily','both'):
                daily_data = await self.get_daily_usage_data()
            if mode in ('hourly','both'):
                hourly_data = await self.get_hourly_usage_data(target_date=target_date_obj)

            self.save(
                daily=daily_data if mode!='hourly' else None,
                hourly=hourly_data if mode!='daily' else None,
                save_format=save_format
            )
            result = {}
            if daily_data is not None: result['daily'] = daily_data
            if hourly_data is not None: result['hourly'] = hourly_data
            return result
        except AuthenticationRequiredError:
            raise
        except Exception as e:
            await self._notify_alert("爬取过程中发生未捕获错误", {"exception": str(e)})
            logger.error(f"爬取过程中发生错误: {e}")
            raise
        finally:
            await self.close()
