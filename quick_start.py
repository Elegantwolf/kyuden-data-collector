"""
快速开始指南
"""

print("""
🔌 九州电力数据收集器 - 快速开始指南
================================================

第一步：配置登录信息
-----------------
编辑 config.py 文件，填入您的九州电力账户信息：

USERNAME = "your_username_here"  # 替换为您的用户名
PASSWORD = "your_password_here"  # 替换为您的密码

第二步：运行爬虫
--------------
python example.py

或者直接运行：
python -c "import asyncio; from kyuden_scraper import KyudenScraper; from config import USERNAME, PASSWORD; asyncio.run(KyudenScraper().scrape(USERNAME, PASSWORD))"

第三步：查看结果
--------------
数据将保存在当前目录下：
- kyuden_usage_YYYYMMDD_HHMMSS.csv  # CSV 格式
- kyuden_usage_YYYYMMDD_HHMMSS.json # JSON 格式

测试数据解析（无需登录）：
python test_parser.py

注意事项：
- 确保用户名和密码正确
- 首次运行可能需要等待浏览器下载
- 建议在网络稳定的环境下运行

================================================
祝您使用愉快！
""")

if __name__ == "__main__":
    pass
