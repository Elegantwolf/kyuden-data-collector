# main module for Kyuden electricity usage scraper
import asyncio
import json
import html
from datetime import datetime, date
import pandas as pd
from playwright.async_api import async_playwright
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, Any, Union

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KyudenScraper:
    def __init__(
        self,
        storage_state_path: Optional[Union[str, Path]] = None,
        alert_handler: Optional[Callable[[str, Dict[str, Any]], Union[None, Awaitable[None]]]] = None,
        max_login_retries: int = 2,
    ):
        self.base_url = "https://my.kyuden.co.jp"
        self.login_url = f"{self.base_url}/member"  # 登录页面更精确
        self.chart_url = f"{self.base_url}/member/chart_days_current"
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._headless = True

        # 新增：登录状态复用与告警配置
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.alert_handler = alert_handler
        self.max_login_retries = max(1, max_login_retries)
        
    async def init_browser(self, headless=True, use_storage_state: bool = True):
        """初始化浏览器（可加载 storage state 以复用登录态）"""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=headless,
            args=['--no-first-run', '--disable-dev-shm-usage'] if headless else []
        )
        self._headless = headless
        storage_state = None
        if use_storage_state and self.storage_state_path and self.storage_state_path.exists():
            storage_state = str(self.storage_state_path)
            logger.info(f"加载登录状态: {self.storage_state_path}")

        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            storage_state=storage_state
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
            await self.page.goto(self.base_url+"/member/account", timeout=10000)
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_selector('button.fs-top_card__detail_button.-hourly, button.fs-top_card__detail_button.-daily',
                    timeout=2000
                )
            return True
        except Exception as e:
            logger.warning(f"登录状态检查异常: {e}")
            return False

    async def login(self, username, password):
        """执行一次显式登录，并在成功后保存 storage state"""
        try:
            logger.info("开始登录...")
            await self.page.goto(self.login_url)
            await self.page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(1)  # 等待 JS 渲染

            email_input = await self.page.query_selector('input[name="body_1$TxtKaiinId"]')
            if not email_input:
                logger.error("未找到邮箱输入框")
                await self.page.screenshot(path='email_input_not_found.png')
                return False
            await email_input.fill(username)

            password_input = await self.page.query_selector('input[name="body_1$TxtPasswd"]')
            if not password_input:
                logger.error("未找到密码输入框")
                await self.page.screenshot(path='password_input_not_found.png')
                return False
            await password_input.fill(password)
            await asyncio.sleep(1)

            submit_button = await self.page.query_selector('button.fs-submit')
            if not submit_button:
                logger.error("未找到登录提交按钮")
                await self.page.screenshot(path='submit_button_not_found.png')
                return False
            await submit_button.click()

            try:
                await self.page.wait_for_url('**/member/**', timeout=15000)
            except Exception:
                # 有时不会稳定跳转，尽量容错
                await asyncio.sleep(1)

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

    async def ensure_logged_in(self, username: str, password: str) -> bool:
        """先尝试复用 storage state；失败则退回重登，支持最大重试次数"""
        # 1) 尝试复用状态
        if await self.is_logged_in():
            logger.info("检测到已登录（复用状态）")
            return True

        # 2) 回退显式登录 + 重试
        for attempt in range(1, self.max_login_retries + 1):
            logger.info(f"尝试显式登录（第 {attempt}/{self.max_login_retries} 次）")
            if await self.login(username, password):
                return True

            if attempt == 1 and self.storage_state_path:
                logger.warning("使用 storage state 登录失败，回退到无状态登录并刷新 storage_state.json")
                try:
                    if self.storage_state_path.exists():
                        self.storage_state_path.unlink()
                        logger.info(f"已删除失效的 storage state: {self.storage_state_path}")
                except Exception as remove_err:
                    logger.warning(f"删除 storage state 失败: {remove_err}")
                await self.close()
                await self.init_browser(headless=self._headless, use_storage_state=False)

            await asyncio.sleep(min(2 * attempt, 5))  # 退避

        await self._notify_alert("登录失败，达到最大重试次数", {"stage": "login"})
        return False
            
    async def get_daily_usage_data(self):
        """获取每日用电量数据"""
        await self.page.goto(self.base_url+"/member/account", timeout=10000)
        await self.page.click('button.fs-top_card__detail_button.-daily')
        await self.page.wait_for_load_state('domcontentloaded')
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
            return []
            
    async def get_hourly_usage_data(self, target_date: Optional[date] = None):
        """获取每小时用电量数据（允许传入目标日期归属）"""
        await self.page.wait_for_load_state('networkidle')
        await self.page.goto(self.base_url+"/member/account", timeout=10000)
        await self.page.click('button.fs-top_card__detail_button.-hourly')
        await self.page.wait_for_load_state('domcontentloaded')
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
            return []

    def parse_usage_data(self, data):
        """解析每日用电量数据"""
        try:
            dates = data['shiyoKikan'][1:]  # 跳过第一个'x'
            usage_values = data['columns'][0][1:]  # 跳过标题
            parsed_data = []
            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month
            for date_str, usage in zip(dates, usage_values):
                if usage is None:
                    continue
                if '/' in date_str:
                    month, day = map(int, date_str.split('/'))
                    year = current_year
                    if month < current_month:
                        year = current_year + 1
                    elif month > current_month:
                        year = current_year - 1
                    if current_month == 9 and month == 8:
                        year = current_year
                    parsed_data.append({
                        'date': date(year, month, day),
                        'date_str': date_str,
                        'usage_kwh': usage,
                        'timestamp': datetime.now()
                    })
            logger.info(f"每日数据解析完成，共{len(parsed_data)}条")
            return parsed_data
        except Exception as e:
            logger.error(f"解析每日数据失败: {e}")
            return []
            
    def parse_hourly_usage_data(self, data, target_date=None):
        """解析每小时用电量数据"""
        try:
            if target_date is None:
                target_date = date.today()
            columns = data.get('columns', [])
            if not columns or not columns[0]:
                logger.warning("列数据为空")
                return []
            raw_values = columns[0][1:]
            parsed = []
            for hour, val in enumerate(raw_values):
                if val is None:
                    continue
                parsed.append({
                    'date': target_date,
                    'date_str': target_date.isoformat(),
                    'hour': hour,
                    'usage_kwh': val,
                    'timestamp': datetime.now()
                })
            logger.info(f"每小时数据解析完成，共{len(parsed)}条")
            return parsed
        except Exception as e:
            logger.error(f"解析每小时数据失败: {e}")
            return []
            
    def _save_dataset(self, data, prefix, ext):
        if not data:
            logger.warning(f"{prefix} 没有数据可保存")
            return None
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{prefix}_{ts}.{ext}"
        if ext == 'csv':
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
        else:
            json_data = []
            for item in data:
                obj = item.copy()
                if isinstance(obj.get('date'), date):
                    obj['date'] = obj['date'].isoformat()
                if isinstance(obj.get('timestamp'), datetime):
                    obj['timestamp'] = obj['timestamp'].isoformat()
                json_data.append(obj)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
        logger.info(f"保存文件: {filename}")
        return filename

    def save(self, daily=None, hourly=None, save_format='both'):
        results = {}
        # 新增：支持 'none' 以关闭保存
        if save_format in ['csv','both']:
            if daily is not None:
                results['daily_csv'] = self._save_dataset(daily, 'kyuden_daily', 'csv')
            if hourly is not None:
                results['hourly_csv'] = self._save_dataset(hourly, 'kyuden_hourly', 'csv')
        if save_format in ['json','both']:
            if daily is not None:
                results['daily_json'] = self._save_dataset(daily, 'kyuden_daily', 'json')
            if hourly is not None:
                results['hourly_json'] = self._save_dataset(hourly, 'kyuden_hourly', 'json')
        if save_format == 'none':
            logger.info("已关闭文件保存（save_format=none）")
        return results
            
    async def close(self):
        if self.browser:
            await self.browser.close()
            logger.info("浏览器已关闭")
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Playwright 已停止")
            
    async def scrape(
        self,
        username,
        password,
        mode='daily',
        save_format='both',
        headless=True,
        hourly_target_date: Optional[Union[str, date]] = None,
        storage_state_path: Optional[Union[str, Path]] = None,
        max_login_retries: Optional[int] = None,
        alert_handler: Optional[Callable[[str, Dict[str, Any]], Union[None, Awaitable[None]]]] = None,
    ):
        """
        完整爬取流程
        mode: 'daily' | 'hourly' | 'both'
        hourly_target_date: 可传入 date 或 'YYYY-MM-DD' 字符串，控制小时数据的日期归属
        """
        assert mode in ('daily','hourly','both')
        # 允许在 scrape 级别覆盖构造参数
        if storage_state_path is not None:
            self.storage_state_path = Path(storage_state_path)
        if max_login_retries is not None:
            self.max_login_retries = max(1, int(max_login_retries))
        if alert_handler is not None:
            self.alert_handler = alert_handler

        # 解析 hourly 的 target_date
        target_date_obj: Optional[date] = None
        if isinstance(hourly_target_date, str) and hourly_target_date:
            try:
                target_date_obj = date.fromisoformat(hourly_target_date)
            except Exception:
                logger.warning(f"无法解析 hourly_target_date={hourly_target_date}，将使用系统日期")
        elif isinstance(hourly_target_date, date):
            target_date_obj = hourly_target_date

        try:
            await self.init_browser(headless=headless, use_storage_state=True)
            if not await self.ensure_logged_in(username, password):
                logger.error("登录失败，终止")
                return {}

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
        except Exception as e:
            await self._notify_alert("爬取过程中发生未捕获错误", {"exception": str(e)})
            logger.error(f"爬取过程中发生错误: {e}")
            return {}
        finally:
            await self.close()

async def main():
    import argparse, os
    parser = argparse.ArgumentParser(description='Kyuden data scraper')
    parser.add_argument('--username', '-u', default=os.getenv('KYUDEN_USER','your_username'))
    parser.add_argument('--password', '-p', default=os.getenv('KYUDEN_PASS','your_password'))
    parser.add_argument('--mode', '-m', choices=['daily','hourly','both'], default='both')
    parser.add_argument('--format', '-f', choices=['csv','json','both','none'], default='none')  # 支持 none
    parser.add_argument('--hourly-date', help='小时数据的日期归属，ISO 格式 YYYY-MM-DD', default=None)
    parser.add_argument('--storage-state', default=os.getenv('KYUDEN_STATE','state/.storage_state.json'),
                        help='登录状态文件路径（storage state）')
    parser.add_argument('--max-login-retries', type=int, default=int(os.getenv('KYUDEN_MAX_LOGIN_RETRIES','2')))
    parser.add_argument('--headless', action='store_true', help='Run browser headless (default true)')
    parser.add_argument('--no-headless', action='store_true', help='Force headed mode')
    args = parser.parse_args()

    USERNAME = args.username
    PASSWORD = args.password
    MODE = args.mode
    SAVE_FORMAT = args.format
    HEADLESS = False if args.no_headless else True  # default headless

    if USERNAME == 'your_username' or PASSWORD == 'your_password':
        logger.warning('请提供正确的用户名和密码 (--username / --password 或环境变量 KYUDEN_USER / KYUDEN_PASS)')
        return

    scraper = KyudenScraper(
        storage_state_path=args.storage_state,
        max_login_retries=args.max_login_retries,
    )
    data = await scraper.scrape(
        USERNAME, PASSWORD,
        mode=MODE,
        save_format=SAVE_FORMAT,
        headless=HEADLESS,
        hourly_target_date=args.hourly_date,
    )
    for k, v in data.items():
        print(f"{k} 数据条数: {len(v)}")
        if v:
            print('示例:', v[0])

if __name__ == "__main__":
    asyncio.run(main())
