"""PyInstaller 入口，保留包内相对导入。"""
from qianniu_assistant.__main__ import main

if __name__ == '__main__':
    raise SystemExit(main())
