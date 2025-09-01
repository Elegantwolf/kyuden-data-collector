"""
九州电力爬虫使用示例
简单易用的接口
"""

import asyncio
from kyuden_scraper import KyudenScraper
import config

async def simple_scrape():
    """简单的爬取示例"""
    scraper = KyudenScraper()
    
    # 使用配置文件中的凭据和设置
    data = await scraper.scrape(
        username=config.USERNAME,
        password=config.PASSWORD,
        save_format=config.SAVE_FORMAT,
        headless=config.HEADLESS  # 使用配置文件中的 HEADLESS 设置
    )
    
    if data:
        print("爬取成功！数据概览：")
        print(f"总共获取 {len(data)} 条记录")
        print("\n最近的用电量数据：")
        
        # 按日期排序并显示最近的数据
        sorted_data = sorted(data, key=lambda x: x['date'], reverse=True)
        for i, item in enumerate(sorted_data[:7]):  # 显示最近7天
            print(f"{item['date']}: {item['usage_kwh']} kWh")
            
        print(f"\n数据已保存到当前目录")
    else:
        print("爬取失败，请检查登录凭据和网络连接")

if __name__ == "__main__":
    # 运行爬虫
    asyncio.run(simple_scrape())
