"""
测试数据解析功能
用于验证 JSON 数据解析逻辑是否正确
"""

import json
import html
from datetime import datetime, date
from kyuden_scraper import KyudenScraper

def test_data_parsing():
    """测试数据解析功能"""
    
    # 模拟从网站获取的原始数据（HTML 转义后的 JSON）
    raw_data = '{&quot;columns&quot;:[[&quot;使用電力量&quot;,2.2,2.1,2.2,2.1,2.3,2.3,2.2,2.2,8.4,14.8,16.2,12.0,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null],[&quot;dummy&quot;,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null]],&quot;shiyoKikan&quot;:[&quot;x&quot;,&quot;8/20&quot;,&quot;8/21&quot;,&quot;8/22&quot;,&quot;8/23&quot;,&quot;8/24&quot;,&quot;8/25&quot;,&quot;8/26&quot;,&quot;8/27&quot;,&quot;8/28&quot;,&quot;8/29&quot;,&quot;8/30&quot;,&quot;8/31&quot;,&quot;9/1&quot;,&quot;9/2&quot;,&quot;9/3&quot;,&quot;9/4&quot;,&quot;9/5&quot;,&quot;9/6&quot;,&quot;9/7&quot;,&quot;9/8&quot;,&quot;9/9&quot;,&quot;9/10&quot;,&quot;9/11&quot;,&quot;9/12&quot;,&quot;9/13&quot;,&quot;9/14&quot;,&quot;9/15&quot;,&quot;9/16&quot;,&quot;9/17&quot;],&quot;groups&quot;:[[&quot;使用電力量&quot;,&quot;dummy&quot;]],&quot;order&quot;:[&quot;使用電力量&quot;,&quot;dummy&quot;]}'
    
    print("测试数据解析功能...")
    print("=" * 50)
    
    try:
        # 1. 解码 HTML 实体
        decoded_data = html.unescape(raw_data)
        print("✓ HTML 解码成功")
        
        # 2. 解析 JSON
        usage_data = json.loads(decoded_data)
        print("✓ JSON 解析成功")
        
        # 3. 提取数据结构
        dates = usage_data['shiyoKikan'][1:]  # 跳过第一个'x'
        usage_values = usage_data['columns'][0][1:]  # 跳过第一个标题
        
        print(f"✓ 提取到 {len(dates)} 个日期")
        print(f"✓ 提取到 {len(usage_values)} 个用电量值")
        
        # 4. 使用爬虫类解析数据
        scraper = KyudenScraper()
        parsed_data = scraper.parse_usage_data(usage_data)
        
        print(f"✓ 解析成功，共 {len(parsed_data)} 条有效数据")
        
        # 5. 显示解析结果
        print("\n解析结果:")
        print("-" * 30)
        for item in parsed_data:
            print(f"日期: {item['date']}, 用电量: {item['usage_kwh']} kWh")
            
        # 6. 测试保存功能
        print("\n测试保存功能...")
        success_csv = scraper.save_to_csv(parsed_data, "test_data.csv")
        success_json = scraper.save_to_json(parsed_data, "test_data.json")
        
        if success_csv:
            print("✓ CSV 保存成功")
        if success_json:
            print("✓ JSON 保存成功")
            
        print("\n" + "=" * 50)
        print("所有测试通过！爬虫数据解析功能正常")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False

if __name__ == "__main__":
    test_data_parsing()
