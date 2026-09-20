#!/bin/zsh
set -eu

MODE=${1:-hourly}
if [[ "$MODE" != "hourly" && "$MODE" != "daily" ]]; then
  echo "unsupported mode: $MODE" >&2
  exit 2
fi

PROJECT_DIR=${0:A:h:h}
cd "$PROJECT_DIR"
mkdir -p data logs run state secrets

LOG_FILE="$PROJECT_DIR/logs/kyuden-${MODE}.log"
if [[ -f "$LOG_FILE" && $(stat -f %z "$LOG_FILE") -ge 5242880 ]]; then
  mv -f "$LOG_FILE" "${LOG_FILE}.1"
fi

export KYUDEN_PROFILE_DIR="$PROJECT_DIR/state/chrome-profile"
export KYUDEN_LOCK="$PROJECT_DIR/run/collector.lock"
export KYUDEN_BROWSER_CHANNEL=${KYUDEN_BROWSER_CHANNEL:-chrome}
export KYUDEN_HEADLESS=${KYUDEN_HEADLESS:-true}
export TZ=Asia/Tokyo

if [[ -f "$PROJECT_DIR/secrets/kyuden.env" ]]; then
  set -a
  source "$PROJECT_DIR/secrets/kyuden.env"
  set +a
fi

exec "$PROJECT_DIR/.venv/bin/python" -m kyuden --mode "$MODE" \
  --db "$PROJECT_DIR/data/kyuden.sqlite" >> "$LOG_FILE" 2>&1
