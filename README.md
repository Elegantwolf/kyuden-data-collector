# 九州电力个人数据采集器

面向个人、单账户、本地运行的电力数据采集工具。核心采集链路已经实现；当前工作重心是可靠运行和维护，而不是重新开发爬虫。

## 项目目标

定期复用专用 Chrome 登录会话，采集当前账期每日用电量和当前小时图表，幂等写入本地 SQLite。登录过期或出现验证时暂停采集，通知用户人工续期，再恢复后续任务。

允许人工参与：目标是平均每周不超过一次登录干预，但这需要实际运行观察，不能承诺网站会话有效期，也不以绕过验证码为目标。详见 [目标与验收](docs/PROJECT_GOALS.md)。

## 已有能力与边界

- 专用持久化 Chrome profile；定时任务默认不使用账号密码登录。
- 人工登录命令及 macOS 双击入口 `manual_login.command`。
- 每日／每小时采集、SQLite UPSERT、CSV／JSON 导出接口。
- 进程锁、登录失效退出码、可配置 webhook 通知。
- 当前周期日期解析、JST 时间、空值跳过和异常数据检查。

已有端到端采集验证不等于长期可靠性验证。通知需要配置接收端；计划任务模板需要用户安装。小时采集没有历史页面导航，`--hourly-date` 只接受日本时区当天，不能用于历史回填。每日解析限定当前账期（非空读数最多追溯 62 天）。小时图表日期目前依赖当天假设，仍需与网页日期核对，尤其是跨午夜采集。

## 安装与使用

需要 Python 3.10+、本机 Google Chrome（macOS/Linux；进程锁使用 fcntl）。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m kyuden --interactive-login
.venv/bin/python -m kyuden --mode both
```

默认数据库：`data/kyuden.sqlite`；默认会话：`state/chrome-profile`。默认路径相对项目根目录，不受启动目录影响。已有数据库应使用 `--db /绝对路径/原数据库`，不会自动迁移或合并旧数据库。

```sh
.venv/bin/python -m kyuden --mode daily --db /absolute/path/usage.sqlite
.venv/bin/python -m kyuden --mode hourly --headed
.venv/bin/python -m unittest discover -v
```

旧入口 `python collector.py` 和 `python kyuden_scraper.py` 委托给同一个 CLI；原有类导入仍然可用。旧抓取器命令行参数不保证兼容，以 `--help` 为准。

### macOS 长期运行

安装脚本会先卸载同名旧任务，再原位更新链接，因此重复执行不会创建第二套任务：

```sh
./scripts/install_macos_launchagents.zsh
launchctl print "gui/$(id -u)/com.kyuden.collector.hourly"
```

小时任务在每小时第 5 分钟运行；每日任务在 01:05 运行。单个日志超过 5 MiB 时保留一份 `.1`，避免无限增长。部署前如需清空旧数据，应先将 `data/` 与 `logs/` 移到仓库外的私有归档；安装脚本不会自行删除用户数据。

## 登录失效与通知

退出码：0 为流程成功（不保证当天数据完整），20 为需要人工登录，1 为其他失败。
收到登录提示后，运行人工登录命令或双击 `manual_login.command`，完成网站验证；后续采集复用相同 profile。人工窗口和采集共用锁，避免并发损坏会话。

可选环境变量：

| 变量 | 用途 |
| --- | --- |
| KYUDEN_PROFILE_DIR | 专用 Chrome profile 路径 |
| KYUDEN_BROWSER_CHANNEL | 默认 chrome |
| KYUDEN_HEADLESS | 默认 true；设 false 显示窗口 |
| KYUDEN_AUTH_TIMEOUT | 人工登录等待秒数，默认 900 |
| KYUDEN_LOCK / KYUDEN_LOCK_TIMEOUT | 锁路径／等待秒数，默认 180 |
| KYUDEN_NOTIFY_WEBHOOK | 接收 JSON POST 的通知地址 |

profile、环境文件、数据库、截图和采集结果都是敏感本地数据，不应提交 Git。不要复用日常 Chrome profile，不需要在代码中保存密码。webhook 地址也可能含密钥。日志／告警可能带运行上下文，只应发送给可信接收端。

## 代码结构

| 模块 | 职责 |
| --- | --- |
| kyuden/cli.py | 参数、锁、退出码 |
| kyuden/service.py | 采集与入库编排 |
| kyuden/scraper.py | 浏览器、会话、网页读取 |
| kyuden/parsing.py | 纯数据解析与校验 |
| kyuden/storage.py | SQLite schema 与 UPSERT |
| kyuden/export.py | CSV／JSON 导出 |
| kyuden/notifications.py、locking.py、settings.py | 运行支持 |
| legacy/ | 早期实验版本，仅供参考，不属于支持入口 |

数据库表结构保持兼容；本轮没有删除历史数据或浏览器会话。测试均为离线测试，不会打开浏览器或提交凭据。
