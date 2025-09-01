"""
调试版本 - 测试新的登录流程
"""

import asyncio
from kyuden_scraper import KyudenScraper
import config
import logging

# 设置更详细的日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_new_login():
    """测试新的登录流程"""
    
    if config.USERNAME == "your_username_here":
        print("❌ 请在 config.py 中设置正确的用户名和密码")
        return
    
    scraper = KyudenScraper()
    
    try:
        # 初始化浏览器（非无头模式）
        await scraper.init_browser(headless=config.HEADLESS)
        print("✅ 浏览器已启动")
        
        # 测试登录流程
        success = await scraper.login(config.USERNAME, config.PASSWORD)
        
        if success:
            print("✅ 登录成功！")
            
            # 如果登录成功，尝试获取数据
            print("🔄 尝试获取用电量数据...")
            data = await scraper.get_daily_usage_data()
            
            if data:
                print(f"✅ 成功获取 {len(data)} 条数据:")
                for item in data[:5]:  # 显示前5条
                    print(f"  📅 {item['date']}: {item['usage_kwh']} kWh")
                    
                # 保存数据
                scraper.save_to_csv(data, "test_real_data.csv")
                scraper.save_to_json(data, "test_real_data.json")
                print("💾 数据已保存")
            else:
                print("❌ 获取数据失败")
        else:
            print("❌ 登录失败")
            
        # 暂停一下让用户查看浏览器状态
        print("\n⏸️  登录流程完成，浏览器将保持打开状态30秒供您查看...")
        print("📸 请查看生成的截图文件了解登录过程")
        await asyncio.sleep(30)
        
    except Exception as e:
        print(f"💥 发生错误: {e}")
        
    finally:
        await scraper.close()
        print("🔚 浏览器已关闭")

if __name__ == "__main__":
    asyncio.run(test_new_login())
