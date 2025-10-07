启用步骤（用户级）

目录与权限
mkdir -p ~/kyuden-data-collector/{data,run,state,secrets,systemd}
chmod 700 ~/kyuden-data-collector/secrets
chmod 600 ~/kyuden-data-collector/secrets/kyuden.env
首次验证依赖
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
链接与启用
systemctl --user daemon-reload
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-hourly.service
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-hourly.timer
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-daily.service
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-daily.timer
systemctl --user enable --now kyuden-hourly.timer kyuden-daily.timer
日志与手动触发
journalctl --user -u kyuden-hourly.service -n 200 -f
systemctl --user start kyuden-hourly.service
开机无人登录也运行（可选）
loginctl enable-linger "$USER"




# Kyuden Data Collector (九州电力数据收集器)

一个用于自动收集九州电力网站每日用电量数据的爬虫工具。使用 Python + Playwright 实现，支持模拟登录和数据提取。

## 功能特点

- 🔐 支持自动登录九州电力会员网站
- 📊 自动提取每日用电量数据
- 💾 支持 CSV 和 JSON 格式保存
- 🤖 基于 Playwright 的稳定爬取
- 📝 详细的日志记录
- ⚙️ 可配置的参数设置

## 安装依赖

```bash
# 克隆项目
git clone https://github.com/Elegantwolf/kyuden-data-collector.git
cd kyuden-data-collector

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install
```

## 配置

1. 编辑 `config.py` 文件，填入您的九州电力账户信息：

```python
USERNAME = "your_username_here"  # 您的用户名
PASSWORD = "your_password_here"  # 您的密码
```

2. 可选配置项：
   - `HEADLESS`: 是否无头模式运行（默认 True）
   - `SAVE_FORMAT`: 保存格式 - "csv", "json", "both"（默认 "both"）
   - `DATA_DIR`: 数据保存目录（默认 "data"）

## 使用方法

### 快速开始

```bash
python example.py
```

### 高级用法

```python
import asyncio
from kyuden_scraper import KyudenScraper

async def main():
    scraper = KyudenScraper()
    data = await scraper.scrape("username", "password")
    
    if data:
        print(f"获取了 {len(data)} 条数据")
        for item in data:
            print(f"{item['date']}: {item['usage_kwh']} kWh")

asyncio.run(main())
```

## 数据格式

爬取的数据包含以下字段：

- `date`: 日期（date 对象）
- `date_str`: 原始日期字符串（如 "8/20"）
- `usage_kwh`: 用电量（kWh）
- `timestamp`: 数据获取时间戳

### CSV 格式示例
```csv
date,date_str,usage_kwh,timestamp
2024-08-20,8/20,2.2,2024-09-01 10:30:00
2024-08-21,8/21,2.1,2024-09-01 10:30:00
```

### JSON 格式示例
```json
[
  {
    "date": "2024-08-20",
    "date_str": "8/20",
    "usage_kwh": 2.2,
    "timestamp": "2024-09-01T10:30:00"
  }
]
```

## 工作原理

该爬虫基于以下技术实现：

1. **Playwright**: 用于自动化浏览器操作
2. **登录模拟**: 自动填写登录表单并提交
3. **数据提取**: 从隐藏的 HTML 输入框中提取 JSON 数据
4. **数据解析**: 解析用电量和日期信息
5. **数据保存**: 支持多种格式保存

数据来源：`https://my.kyuden.co.jp/member/chart_days_current` 页面中的隐藏字段 `body_0$Data`

## 注意事项

- ⚠️ 请确保您有合法权限访问九州电力网站
- 🔒 请妥善保管您的登录凭据，不要提交到版本控制系统
- 🌐 爬取频率请适中，避免对网站造成过大负担
- 📋 数据仅供个人使用，请遵守网站使用条款

## 故障排除

1. **登录失败**
   - 检查用户名和密码是否正确
   - 确认网站是否有验证码或其他安全措施

2. **数据获取失败**
   - 检查网络连接
   - 确认网站结构是否发生变化

3. **浏览器启动失败**
   - 确保已正确安装 Playwright 浏览器：`playwright install`

## 开发

### 项目结构
```
kyuden-data-collector/
├── kyuden_scraper.py  # 主爬虫类
├── config.py          # 配置文件
├── example.py         # 使用示例
├── requirements.txt   # 依赖列表
├── data/             # 数据保存目录
└── README.md         # 说明文档
```

### 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。