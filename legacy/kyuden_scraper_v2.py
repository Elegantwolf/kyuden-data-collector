"""
九州电力爬虫 - 简化登录版本
专门针对提供的登录流程设计
"""

import asyncio
import json
import html
from datetime import datetime, date
import pandas as pd
from playwright.async_api import async_playwright
import logging
import config

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KyudenScraperV2:
    def __init__(self):
        self.base_url = "https://my.kyuden.co.jp"
        self.login_page_url = "https://my.kyuden.co.jp/member/"  # 直接使用登录页面URL
        self.chart_url = f"{self.base_url}/member/chart_days_current"
        self.browser = None
        self.context = None
        self.page = None
        
    async def init_browser(self, headless=True):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=headless,
            slow_mo=1000 if not headless else 0  # 非headless模式下减慢操作速度以便观察
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.page = await self.context.new_page()
        logger.info(f"浏览器初始化完成 (headless={headless})")
        
    async def login(self, username, password):
        """登录九州电力网站 - 简化版本"""
        try:
            logger.info("开始登录流程...")
            
            # 直接访问登录页面
            logger.info(f"访问登录页面: {self.login_page_url}")
            await self.page.goto(self.login_page_url, wait_until="networkidle", timeout=30000)
            
            # 等待页面完全加载
            await self.page.wait_for_timeout(3000)
            logger.info(f"当前页面标题: {await self.page.title()}")
            logger.info(f"当前页面URL: {self.page.url}")
            
            # 截图查看当前页面状态
            await self.page.screenshot(path='current_page.png')
            logger.info("已保存当前页面截图: current_page.png")
            
            # 1. 查找并填写邮箱
            logger.info("查找邮箱输入框...")
            email_selectors = [
                'input[name="body_1$TxtKaiinId"]',
                'input[id="body_1_TxtKaiinId"]',
                'input[type="email"]',
                'input.fs-form_item__textbox[type="email"]'
            ]
            
            email_input = None
            for selector in email_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                    email_input = await self.page.query_selector(selector)
                    if email_input:
                        logger.info(f"找到邮箱输入框: {selector}")
                        break
                except:
                    continue
            
            if not email_input:
                logger.error("未找到邮箱输入框")
                return False
            
            # 清空并输入邮箱
            logger.info("输入邮箱地址...")
            await email_input.click()
            await email_input.fill('')  # 清空
            await email_input.type(username, delay=100)  # 模拟真实输入
            
            # 2. 查找并填写密码
            logger.info("查找密码输入框...")
            password_selectors = [
                'input[name="body_1$TxtPasswd"]',
                'input[id="body_1_TxtPasswd"]', 
                'input[type="password"]',
                'input.fs-form_item__textbox[type="password"]'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                    password_input = await self.page.query_selector(selector)
                    if password_input:
                        logger.info(f"找到密码输入框: {selector}")
                        break
                except:
                    continue
            
            if not password_input:
                logger.error("未找到密码输入框")
                return False
            
            # 清空并输入密码
            logger.info("输入密码...")
            await password_input.click()
            await password_input.fill('')  # 清空
            await password_input.type(password, delay=100)  # 模拟真实输入
            
            # 3. 查找并点击登录按钮
            logger.info("查找登录按钮...")
            login_selectors = [
                'button.fs-submit',
                'button[onclick="checkValue();"]',
                'button[type="button"].fs-submit',
                '.fs-submit'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                    login_button = await self.page.query_selector(selector)
                    if login_button:
                        logger.info(f"找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                logger.error("未找到登录按钮")
                return False
            
            # 登录前截图
            await self.page.screenshot(path='before_login.png')
            logger.info("已保存登录前截图: before_login.png")
            
            # 点击登录按钮
            logger.info("点击登录按钮...")
            await login_button.click()
            
            # 等待登录结果
            logger.info("等待登录处理...")
            await self.page.wait_for_timeout(5000)  # 等待5秒让登录处理完成
            
            # 登录后截图
            await self.page.screenshot(path='after_login.png')
            logger.info("已保存登录后截图: after_login.png")
            
            # 检查登录结果
            current_url = self.page.url
            logger.info(f"登录后URL: {current_url}")
            
            # 如果URL包含member并且不是登录页面，则认为登录成功
            if '/member/' in current_url and current_url != self.login_page_url:
                logger.info("登录成功！")
                return True
            else:
                # 检查是否有错误信息
                logger.warning("登录可能失败，检查错误信息...")
                error_selectors = ['.error', '.alert', '.warning', '.message']
                for selector in error_selectors:
                    try:
                        error_elements = await self.page.query_selector_all(selector)
                        for element in error_elements:
                            error_text = await element.text_content()
                            if error_text and error_text.strip():
                                logger.error(f"错误信息: {error_text.strip()}")
                    except:
                        continue
                
                return False
            
        except Exception as e:
            logger.error(f"登录过程中发生错误: {e}")
            await self.page.screenshot(path='login_error.png')
            return False
    
    async def get_daily_usage_data(self):
        """获取每日用电量数据"""
        try:
            logger.info("获取每日用电量数据...")
            
            # 导航到图表页面
            await self.page.goto(self.chart_url)
            
            # 等待页面加载完成
            await self.page.wait_for_selector('input[name="body_0$Data"]', timeout=10000)
            
            # 获取隐藏输入框中的数据
            data_element = await self.page.query_selector('input[name="body_0$Data"]')
            if not data_element:
                raise Exception("未找到数据元素")
                
            data_value = await data_element.get_attribute('value')
            if not data_value:
                raise Exception("数据为空")
                
            # 解码HTML实体
            decoded_data = html.unescape(data_value)
            
            # 解析JSON数据
            usage_data = json.loads(decoded_data)
            logger.info("成功获取数据")
            
            return self.parse_usage_data(usage_data)
            
        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            return None
    
    def parse_usage_data(self, data):
        """解析用电量数据"""
        try:
            # 提取日期和用电量数据
            dates = data['shiyoKikan'][1:]  # 跳过第一个'x'
            usage_values = data['columns'][0][1:]  # 跳过第一个标题'使用電力量'
            
            # 创建数据字典
            parsed_data = []
            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month
            
            for i, (date_str, usage) in enumerate(zip(dates, usage_values)):
                if usage is not None:  # 只处理有数据的日期
                    # 解析日期格式，如 "8/20" -> "2025/8/20"
                    if '/' in date_str:
                        month_day = date_str.split('/')
                        month = int(month_day[0])
                        day = int(month_day[1])
                        
                        # 智能判断年份
                        year = current_year
                        
                        if month < current_month:
                            year = current_year + 1
                        elif month > current_month:
                            year = current_year - 1
                        
                        # 特殊情况：如果是9月1日，8月的数据应该是今年的
                        if current_month == 9 and month == 8:
                            year = current_year
                            
                        parsed_date = date(year, month, day)
                        
                        parsed_data.append({
                            'date': parsed_date,
                            'date_str': date_str,
                            'usage_kwh': usage,
                            'timestamp': datetime.now()
                        })
            
            logger.info(f"解析完成，共{len(parsed_data)}条有效数据")
            return parsed_data
            
        except Exception as e:
            logger.error(f"解析数据失败: {e}")
            return []
    
    def save_to_csv(self, data, filename=None):
        """保存数据到CSV文件"""
        if not data:
            logger.warning("没有数据可保存")
            return False
            
        try:
            if filename is None:
                filename = f"kyuden_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            logger.info(f"数据已保存到: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            return False
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            logger.info("浏览器已关闭")
    
    async def scrape(self, username, password, headless=True):
        """完整的爬取流程"""
        try:
            # 初始化浏览器
            await self.init_browser(headless=headless)
            
            # 登录
            if not await self.login(username, password):
                logger.error("登录失败，无法继续")
                return None
                
            # 获取数据
            data = await self.get_daily_usage_data()
            if not data:
                logger.error("获取数据失败")
                return None
                
            # 保存数据
            self.save_to_csv(data)
            
            logger.info("爬取完成")
            return data
            
        except Exception as e:
            logger.error(f"爬取过程中发生错误: {e}")
            return None
            
        finally:
            await self.close()


async def test_login():
    """测试登录功能"""
    if config.USERNAME == "your_username_here" or config.PASSWORD == "your_password_here":
        logger.error("请在config.py中设置正确的用户名和密码")
        return
        
    scraper = KyudenScraperV2()
    
    # 使用非headless模式以便观察
    await scraper.init_browser(headless=config.HEADLESS)
    
    # 尝试登录
    success = await scraper.login(config.USERNAME, config.PASSWORD)
    
    if success:
        logger.info("登录测试成功！")
        # 可以继续获取数据
        data = await scraper.get_daily_usage_data()
        if data:
            logger.info(f"成功获取 {len(data)} 条数据")
            scraper.save_to_csv(data, "test_result.csv")
    else:
        logger.error("登录测试失败")
    
    # 如果是非headless模式，等待一段时间让用户观察
    if not config.HEADLESS:
        logger.info("等待10秒以便观察结果...")
        await asyncio.sleep(10)
    
    await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_login())
