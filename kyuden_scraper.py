"""
九州电力网站爬虫 - 获取每日用电量数据
作者：Assistant
日期：2025-09-01
"""

import asyncio
import json
import html
from datetime import datetime, date
import pandas as pd
from playwright.async_api import async_playwright
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KyudenScraper:
    def __init__(self):
        self.base_url = "https://my.kyuden.co.jp"
        self.login_url = f"{self.base_url}/member/"  # 直接使用登录页面链接
        self.chart_url = f"{self.base_url}/member/chart_days_current"
        self.browser = None
        self.context = None
        self.page = None
        
    async def init_browser(self, headless=True):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=headless,
            # 添加更多启动参数以确保浏览器窗口正确显示
            args=['--no-first-run', '--disable-dev-shm-usage'] if headless else []
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.page = await self.context.new_page()
        logger.info(f"浏览器初始化完成 (headless={headless})")
        

    async def login(self, username, password):
        """登录九州电力网站（增强调试和健壮性）"""
        try:
            logger.info("开始登录...")

            # 第一步：访问主页
            logger.info("访问主页...")
            await self.page.goto(self.login_url)
            await self.page.wait_for_load_state('domcontentloaded')
            # await self.page.wait_for_load_state('networkidle')

            # # 第二步：查找并点击登录按钮
            # logger.info("查找登录按钮...")
            # await self.page.screenshot(path='before_find_login_button.png')
            # login_button = await self.page.query_selector('div.cmn-btn.cmn-btn02 a[href="/member/"]')
            # if not login_button:
            #     logger.warning("未找到预期的首页登录按钮，遍历所有按钮调试...")
            #     all_buttons = await self.page.query_selector_all('a,button')
            #     for idx, btn in enumerate(all_buttons):
            #         try:
            #             outer = await btn.evaluate('(el) => el.outerHTML')
            #             logger.debug(f"按钮{idx}: {outer}")
            #         except Exception:
            #             pass
            #     await self.page.screenshot(path='login_button_not_found.png')
            #     return False

            # logger.info("点击登录按钮...")
            # await login_button.click()
            # await self.page.wait_for_load_state('networkidle')

            # # 第三步：等待登录表单加载
            # logger.info("等待登录表单加载...")
            # await self.page.wait_for_selector('input[name="body_1$TxtKaiinId"]', timeout=10000)

            # 第四步：输入邮箱地址
            logger.info("输入邮箱地址...")
            email_input = await self.page.query_selector('input[name="body_1$TxtKaiinId"]')
            if not email_input:
                logger.error("未找到邮箱输入框")
                await self.page.screenshot(path='email_input_not_found.png')
                return False
            await email_input.fill(username)

            # 第五步：输入密码
            logger.info("输入密码...")
            password_input = await self.page.query_selector('input[name="body_1$TxtPasswd"]')
            if not password_input:
                logger.error("未找到密码输入框")
                await self.page.screenshot(path='password_input_not_found.png')
                return False
            await password_input.fill(password)

            # 第六步：查找并点击登录提交按钮
            logger.info("查找并点击登录提交按钮...")
            await self.page.screenshot(path='before_find_submit_button.png')
            submit_button = await self.page.query_selector('button.fs-submit')
            if not submit_button:
                logger.warning("未找到 button.fs-submit，遍历所有 button 元素调试...")
                all_buttons = await self.page.query_selector_all('button')
                for idx, btn in enumerate(all_buttons):
                    try:
                        btn_class = await btn.get_attribute('class')
                        btn_text = await btn.inner_text()
                        logger.debug(f"button[{idx}] class={btn_class}, text={btn_text}")
                    except Exception:
                        pass
                await self.page.screenshot(path='submit_button_not_found.png')
                return False

            # 截图确认表单填写完成
            await self.page.screenshot(path='before_login_submit.png')

            # 点击登录
            await submit_button.click()

            # 等待登录完成
            logger.info("等待登录完成...")
            try:
                await self.page.wait_for_url('**/member/**', timeout=15000)
                logger.info("登录成功")
                await self.page.screenshot(path='after_login.png')
                return True
            except Exception as wait_error:
                logger.warning(f"等待URL变化超时: {wait_error}")
                error_elements = await self.page.query_selector_all('.error, .alert, .warning')
                if error_elements:
                    for error_elem in error_elements:
                        error_text = await error_elem.inner_text()
                        logger.error(f"登录错误信息: {error_text}")
                await self.page.screenshot(path='login_failed.png')
                current_url = self.page.url
                if 'member' in current_url:
                    logger.info("登录可能成功，当前URL包含member")
                    return True
                return False
        except Exception as e:
            logger.error(f"登录失败: {e}")
            await self.page.screenshot(path='login_exception.png')
            return False
            
    async def get_daily_usage_data(self):
        """获取每日用电量数据"""

        """First go to the chart page"""
        await self.page.wait_for_load_state('networkidle')
        await self.page.click('button.fs-top_card__detail_button.-daily')
        await self.page.wait_for_load_state('domcontentloaded')
        logger.info("导航到图表页面完成")

        try:
            logger.info("获取每日用电量数据...")
            
            # 导航到图表页面
            # await self.page.goto(self.chart_url)
            
            # 等待页面加载完成
            # await self.page.wait_for_selector('input[name="body_0$Data"]', timeout=10000, state="attached")
            
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
            
    async def get_every_hour_usage_data(self):
        """First go to the chart page"""
        await self.page.wait_for_load_state('networkidle')
        await self.page.click('button.fs-top_card__detail_button.-hourly')
        await self.page.wait_for_load_state('domcontentloaded')
        logger.info("导航到每小时图表页面完成")
        
        try:
            logger.info("获取每小时用电量数据...")
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
            logger.error(f"获取每小时用电量数据失败: {e}")
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
                        
                        # 智能判断年份：
                        # 1. 如果月份等于当前月份，使用当前年份
                        # 2. 如果月份小于当前月份，可能是下一年的数据（跨年显示）
                        # 3. 如果月份大于当前月份，可能是去年的数据
                        year = current_year
                        
                        if month < current_month:
                            # 月份小于当前月份，可能是下一年
                            year = current_year + 1
                        elif month > current_month:
                            # 月份大于当前月份，可能是去年
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
            
    def save_to_json(self, data, filename=None):
        """保存数据到JSON文件"""
        if not data:
            logger.warning("没有数据可保存")
            return False
            
        try:
            if filename is None:
                filename = f"kyuden_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
            # 转换date对象为字符串以便JSON序列化
            json_data = []
            for item in data:
                json_item = item.copy()
                json_item['date'] = item['date'].isoformat()
                json_item['timestamp'] = item['timestamp'].isoformat()
                json_data.append(json_item)
                
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
                
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
            
    async def scrape(self, username, password, save_format='both', headless=True):
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
            if save_format in ['csv', 'both']:
                self.save_to_csv(data)
                
            if save_format in ['json', 'both']:
                self.save_to_json(data)
                
            logger.info("爬取完成")
            return data
            
        except Exception as e:
            logger.error(f"爬取过程中发生错误: {e}")
            return None
            
        finally:
            await self.close()


async def main():
    """主函数 - 示例用法"""
    # 注意：请替换为您的实际登录凭据
    USERNAME = "your_username"  # 替换为您的用户名
    PASSWORD = "your_password"  # 替换为您的密码
    
    if USERNAME == "your_username" or PASSWORD == "your_password":
        logger.warning("请在代码中设置正确的用户名和密码")
        return
        
    scraper = KyudenScraper()
    data = await scraper.scrape(USERNAME, PASSWORD)
    
    if data:
        print(f"成功获取 {len(data)} 条数据:")
        for item in data:
            print(f"日期: {item['date']}, 用电量: {item['usage_kwh']} kWh")


if __name__ == "__main__":
    asyncio.run(main())
