import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='千牛本地助手 · 自用免费版')
    parser.add_argument('--diagnose',action='store_true',help='只读检测，输出 JSON；不打开界面')
    parser.add_argument('--include-names',action='store_true',help='报告包含控件名称，可能含聊天文字')
    parser.add_argument('--output',type=Path,help='将检测结果保存为 UTF-8 JSON，不使用标准输出')
    parser.add_argument('--data-dir',type=Path,help='指定本地数据目录')
    parser.add_argument('--screenshot',type=Path,help='保存界面截图后退出，用于启动检查')
    args = parser.parse_args()
    if args.diagnose:
        from .diagnostics import diagnose, save_report
        report = diagnose(args.include_names)
        if args.output:
            save_report(args.output, report)
            return 0
        # Windows stdout may use a legacy code page; child protocol is UTF-8.
        if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
        if sys.stdout is not None:
            print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from .store import Store
    from .ui import MainWindow
    data = args.data_dir or (Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'QianniuLocalAssistant')
    app = QApplication(sys.argv[:1]); app.setApplicationName('千牛本地助手')
    window = MainWindow(Store(data/'assistant.sqlite3')); window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True,exist_ok=True)
            ok = window.grab().save(str(args.screenshot)); app.exit(0 if ok else 1)
        QTimer.singleShot(300,capture)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
