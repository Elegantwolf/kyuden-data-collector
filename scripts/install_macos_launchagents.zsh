#!/bin/zsh
set -eu

PROJECT_DIR=${0:A:h:h}
AGENT_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LABELS=(com.kyuden.collector.hourly com.kyuden.collector.daily)

mkdir -p "$AGENT_DIR" "$PROJECT_DIR/data" "$PROJECT_DIR/logs" \
  "$PROJECT_DIR/run" "$PROJECT_DIR/state" "$PROJECT_DIR/secrets"
chmod 700 "$PROJECT_DIR/state" "$PROJECT_DIR/secrets"
chmod +x "$PROJECT_DIR/scripts/run_macos_collector.zsh"

for label in $LABELS; do
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  ln -sfn "$PROJECT_DIR/LaunchAgent/$label.plist" "$AGENT_DIR/$label.plist"
  launchctl bootstrap "$DOMAIN" "$AGENT_DIR/$label.plist"
done

echo "Installed one hourly and one daily Kyuden LaunchAgent."
