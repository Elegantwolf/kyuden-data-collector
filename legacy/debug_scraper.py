"""
调试版本的爬虫 - 用于排查登录问题
"""

import asyncio
import json
import html
from datetime import datetime, date
import pandas as pd
from playwright.async_api import async_playwright
import logging
import config

# 设置更详细的日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KyudenScraperDebug:
    def __init__(self):
        self.base_url = "https://my.kyuden.co.jp"
        self.login_url = f"{self.base_url}/member/login"
        self.chart_url = f"{self.base_url}/member/chart_days_current"
        self.browser = None
        self.context = None
        self.page = None
        
    async def init_browser(self, headless=True):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=headless,
            slow_mo=1000 if not headless else 0,  # 非无头模式时减慢操作速度便于观察
            args=['--no-first-run', '--disable-dev-shm-usage'] if headless else []
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={'width': 1280, 'height': 720}  # 设置窗口大小
        )
        self.page = await self.context.new_page()
        
        # 添加页面事件监听
        self.page.on("console", lambda msg: logger.info(f"浏览器控制台: {msg.text}"))
        self.page.on("pageerror", lambda exception: logger.error(f"页面错误: {exception}"))
        
        logger.info(f"浏览器初始化完成 (headless={headless})")
        
    async def debug_login_page(self):
        """调试登录页面，查看页面结构"""
        try:
            logger.info("访问登录页面...")
            await self.page.goto(self.login_url, wait_until='networkidle')
            
            # 等待页面完全加载
            await self.page.wait_for_load_state('networkidle')
            
            # 获取页面标题
            title = await self.page.title()
            logger.info(f"页面标题: {title}")
            
            # 截图（如果不是无头模式）
            if not config.HEADLESS:
                await self.page.screenshot(path="login_page_debug.png")
                logger.info("已保存登录页面截图: login_page_debug.png")
            
            # 查找所有输入框
            inputs = await self.page.query_selector_all('input')
            logger.info(f"找到 {len(inputs)} 个输入框:")
            
            for i, input_elem in enumerate(inputs):
                input_type = await input_elem.get_attribute('type')
                input_name = await input_elem.get_attribute('name')
                input_id = await input_elem.get_attribute('id')
                input_placeholder = await input_elem.get_attribute('placeholder')
                
                logger.info(f"  输入框 {i+1}: type={input_type}, name={input_name}, id={input_id}, placeholder={input_placeholder}")
            
            # 查找所有表单
            forms = await self.page.query_selector_all('form')
            logger.info(f"找到 {len(forms)} 个表单")
            
            # 查找可能的登录按钮
            buttons = await self.page.query_selector_all('button, input[type="submit"], input[type="button"]')
            logger.info(f"找到 {len(buttons)} 个按钮:")
            
            for i, button in enumerate(buttons):
                button_text = await button.text_content()
                button_value = await button.get_attribute('value')
                button_type = await button.get_attribute('type')
                
                logger.info(f"  按钮 {i+1}: text='{button_text}', value='{button_value}', type={button_type}")
            
            # 输出页面 HTML（部分）
            page_content = await self.page.content()
            logger.debug(f"页面内容长度: {len(page_content)} 字符")
            
            return True
            
        except Exception as e:
            logger.error(f"调试登录页面失败: {e}")
            return False
            
    async def attempt_login(self, username, password):
        """尝试登录，使用调试信息"""
        try:
            logger.info("开始尝试登录...")
            
            # 可能的用户名字段名
            username_selectors = [
                'input[name="username"]',
                'input[name="user"]',
                'input[name="loginId"]',
                'input[name="login_id"]',
                'input[name="email"]',
                'input[type="email"]',
                'input[id*="user"]',
                'input[id*="mail"]',
                'input[id*="login"]'
            ]
            
            # 可能的密码字段名
            password_selectors = [
                'input[name="password"]',
                'input[name="passwd"]',
                'input[name="pass"]',
                'input[type="password"]',
                'input[id*="pass"]'
            ]
            
            username_field = None
            password_field = None
            
            # 查找用户名字段
            for selector in username_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        username_field = element
                        logger.info(f"找到用户名字段: {selector}")
                        break
                except:
                    continue
                    
            # 查找密码字段
            for selector in password_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        password_field = element
                        logger.info(f"找到密码字段: {selector}")
                        break
                except:
                    continue
            
            if not username_field:
                logger.error("未找到用户名输入框")
                return False
                
            if not password_field:
                logger.error("未找到密码输入框")
                return False
            
            # 填写表单
            logger.info("填写用户名...")
            await username_field.fill(username)
            
            logger.info("填写密码...")
            await password_field.fill(password)
            
            # 在非无头模式下暂停，让用户看到填写过程
            if not config.HEADLESS:
                logger.info("暂停2秒让您看到表单填写...")
                await self.page.wait_for_timeout(2000)
            
            # 查找并点击登录按钮
            login_button_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'button:has-text("ログイン")',
                'button:has-text("login")',
                'input[value*="ログイン"]',
                'input[value*="login"]',
                '.login-button',
                '#login-button'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        login_button = element
                        logger.info(f"找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                logger.error("未找到登录按钮")
                return False
            
            logger.info("点击登录按钮...")
            await login_button.click()
            
            # 等待页面跳转
            logger.info("等待登录结果...")
            
            try:
                # 等待页面跳转到会员页面或出现错误信息
                await self.page.wait_for_load_state('networkidle', timeout=15000)
                
                current_url = self.page.url
                logger.info(f"当前URL: {current_url}")
                
                # 检查是否成功跳转到会员页面
                if '/member/' in current_url and 'login' not in current_url:
                    logger.info("登录成功！")
                    return True
                else:
                    # 查找错误信息
                    error_selectors = [
                        '.error', '.alert', '.warning', 
                        '[class*="error"]', '[class*="alert"]',
                        'span[style*="color: red"]', 'div[style*="color: red"]'
                    ]
                    
                    for selector in error_selectors:
                        try:
                            error_elem = await self.page.query_selector(selector)
                            if error_elem:
                                error_text = await error_elem.text_content()
                                if error_text and error_text.strip():
                                    logger.error(f"找到错误信息: {error_text}")
                        except:
                            continue
                    
                    logger.error("登录失败 - 没有跳转到会员页面")
                    return False
                    
            except Exception as e:
                logger.error(f"等待登录结果时出错: {e}")
                return False
                
        except Exception as e:
            logger.error(f"登录过程中发生错误: {e}")
            return False
            
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            logger.info("浏览器已关闭")
            
    async def debug_scrape(self, username, password):
        """调试版爬取流程"""
        try:
            # 初始化浏览器
            await self.init_browser(headless=config.HEADLESS)
            
            # 调试登录页面
            if not await self.debug_login_page():
                logger.error("无法访问登录页面")
                return None
            
            # 在非无头模式下暂停，让用户查看页面
            if not config.HEADLESS:
                logger.info("暂停5秒让您查看登录页面...")
                await self.page.wait_for_timeout(5000)
            
            # 尝试登录
            if not await self.attempt_login(username, password):
                logger.error("登录失败")
                return None
                
            logger.info("调试完成")
            return True
            
        except Exception as e:
            logger.error(f"调试过程中发生错误: {e}")
            return None
            
        finally:
            # 在非无头模式下暂停，让用户看到最终结果
            if not config.HEADLESS:
                logger.info("暂停10秒让您查看结果，然后关闭浏览器...")
                await self.page.wait_for_timeout(10000)
            await self.close()


async def main():
    """主函数 - 调试模式"""
    logger.info("启动调试模式...")
    logger.info(f"HEADLESS 设置: {config.HEADLESS}")
    
    scraper = KyudenScraperDebug()
    result = await scraper.debug_scrape(config.USERNAME, config.PASSWORD)
    
    if result:
        logger.info("调试完成，登录成功")
    else:
        logger.error("调试完成，登录失败")


if __name__ == "__main__":
    asyncio.run(main())
