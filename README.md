# Kyuden Data Collector

A Python-based tool for automatically collecting daily electricity usage data from the Kyuden website.  
Powered by Playwright and SQLite.
Developed as part of my personal exploration in automation and data handling.

## Requirements

- Python 3.11+
- SQLite
- Playwright

## Features

- Human-assisted login and automated data extraction from Kyuden
- Supports daily and hourly data collection
- Saves data in SQLite, CSV, or JSON formats
- Persistent login session via a dedicated Google Chrome profile
- Optional JSON webhook notification when authentication is required
- Configurable via environment variables and CLI
- Automated scheduling via systemd (Linux) or LaunchAgent (macOS)

## Quick Setup

### 1. Clone the Project, Prepare Directories and Permissions

```bash
cd ~
git clone https://github.com/Elegantwolf/kyuden-data-collector.git
mkdir -p ~/kyuden-data-collector/{data,run,state,secrets,logs}
chmod 700 ~/kyuden-data-collector/secrets
```

### 2. Create Virtual Environment and Install Dependencies

```bash
cd ~/kyuden-data-collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The collector uses the locally installed Google Chrome by default. Set
`KYUDEN_BROWSER_CHANNEL=` to use Playwright Chromium instead.

### 3. Authenticate Once in a Dedicated Chrome Profile

Do not put the Kyuden username or password in this repository. Start the
interactive login helper and complete login (including any verification) in
the Chrome window:

```bash
./manual_login.command
# or
.venv/bin/python collector.py --interactive-login
```

The dedicated profile is stored in `state/chrome-profile/`, which is ignored
by Git. Scheduled collection never submits a password. When the session
expires, it exits with status 20 and asks for another interactive login.

### 4. Optional Notification Webhook

Set a webhook URL if another service should receive a JSON POST when login is
required or collection fails:

```bash
mkdir -p secrets
printf 'KYUDEN_NOTIFY_WEBHOOK=https://example.invalid/your-webhook\n' > secrets/kyuden.env
chmod 600 secrets/kyuden.env
```

The payload shape is:

```json
{"message": "登录状态已失效，需要人工登录", "context": {"status": "auth_required"}}
```

Keep `secrets/kyuden.env` local; the entire `secrets/` directory is ignored by
Git.

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

## Future Plans

- Data visualization
- Web data acquisition
- Home Assistant integration
- Email Alarm

## Contributing

Pull requests and issues are welcome!

## License

MIT License. See [LICENSE](LICENSE) for details.
