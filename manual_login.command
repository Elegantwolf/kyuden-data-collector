#!/bin/zsh
set -u

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "未找到 .venv，请先按 README 安装依赖。"
  read -r "?按回车键关闭..."
  exit 1
fi

.venv/bin/python collector.py --interactive-login --auth-timeout 900
status=$?

if [[ $status -eq 0 ]]; then
  echo "人工登录完成，持久化 Chrome profile 已保存。"
else
  echo "人工登录未完成（退出码：$status）。"
fi

read -r "?按回车键关闭..."
exit $status
