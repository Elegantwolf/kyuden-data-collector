# Kyuden Data Collector

A Python-based tool for automatically collecting daily electricity usage data from the Kyuden website.  
Powered by Playwright and SQLite.
Developed as part of my personal exploration in automation and data handling.

## Requirements

- Python 3.11+
- SQLite
- Playwright

## Features

- Automated login and data extraction from Kyuden
- Supports daily and hourly data collection
- Saves data in SQLite, CSV, or JSON formats
- Persistent login session via storage state
- Configurable via environment variables and CLI
- Automated scheduling via systemd (Linux) or LaunchAgent (macOS)

## Quick Setup

### 1. Prepare Directories and Permissions

```bash
mkdir -p ~/kyuden-data-collector/{data,run,state,secrets,systemd,LaunchAgent,logs}
chmod 700 ~/kyuden-data-collector/secrets
chmod 600 ~/kyuden-data-collector/secrets/kyuden.env
```

### 2. Create Virtual Environment and Install Dependencies

```bash
cd ~/kyuden-data-collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Credentials

Edit `~/kyuden-data-collector/secrets/kyuden.env`:

```
KYUDEN_USER=your_username
KYUDEN_PASS=your_password
KYUDEN_MAX_LOGIN_RETRIES=2
```

## Linux: Automated Scheduling with systemd

```bash
systemctl --user daemon-reload
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-hourly.service
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-hourly.timer
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-daily.service
systemctl --user link ~/kyuden-data-collector/systemd/kyuden-daily.timer
systemctl --user enable --now kyuden-hourly.timer kyuden-daily.timer
```

**Manual trigger and logs:**

```bash
systemctl --user start kyuden-hourly.service
journalctl --user -u kyuden-hourly.service -n 200 -f
```

**Optional: Run on boot without login**

```bash
loginctl enable-linger "$USER"
```

## macOS: Automated Scheduling with LaunchAgent

1. **Link LaunchAgent files:**

   ```bash
   ln -sf ~/kyuden-data-collector/LaunchAgent/com.kyuden.collector.hourly.plist ~/Library/LaunchAgents/
   ln -sf ~/kyuden-data-collector/LaunchAgent/com.kyuden.collector.daily.plist ~/Library/LaunchAgents/
   launchctl load -w ~/Library/LaunchAgents/com.kyuden.collector.hourly.plist
   launchctl load -w ~/Library/LaunchAgents/com.kyuden.collector.daily.plist
   ```

2. **Manual trigger and logs:**

   ```bash
   launchctl start com.kyuden.collector.hourly
   tail -f ~/kyuden-data-collector/logs/kyuden-hourly.log
   ```

> All data, logs, and state files are stored in `~/kyuden-data-collector` for easy management and backup.

## Data Format

Each record includes:

- `date`: Date (YYYY-MM-DD)
- `date_str`: Original date string (e.g. "8/20")
- `usage_kwh`: Usage in kWh
- `timestamp`: Data retrieval time


## Security & Notice

- Only use with your own Kyuden account and data.
- Keep credentials safe; never commit secrets to version control.
- Respect Kyuden’s terms of service and avoid excessive scraping.

## Contributing

Pull requests and issues are welcome!

## License

MIT License. See [LICENSE](LICENSE) for details.