"""Print setup commands without reading or requesting credentials."""
if __name__ == "__main__":
    print("""
首次安装：
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
需要本机安装 Google Chrome。
人工登录：
  .venv/bin/python -m kyuden --interactive-login
采集并入库：
  .venv/bin/python -m kyuden --mode both
离线测试：
  .venv/bin/python -m unittest discover -v
""")
