"""版本 2 的只读诊断；发现窗口不等于自动回复已经可用。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import struct
import sys
from .diagnostic_tree import assess_windows


def diagnose(include_names=False, on_progress=None):
    result = {'report_version':2,'target_version':'9.1907n','target_display_version':'9.19.07N (1686)',
              'platform':platform.platform(),
              'python':platform.python_version(),'python_bits':struct.calcsize('P')*8,
              'created':datetime.now(timezone.utc).isoformat(),
              'live_ready':False,'version_verified':False,'windows':[], 'warnings':[],
              'capabilities':dict.fromkeys(['shop_identity','conversation_identity','message_events',
                                          'direction','draft_state','send_confirmation'],False),
              'capabilities_note':'这些能力尚未通过验收；false 不代表已逐项测试并确认不存在。'}
    if on_progress:
        on_progress(result)
    if sys.platform != 'win32':
        result['warnings'].append('当前不是 Windows，无法检测千牛。真实发送保持关闭。')
        return result
    def checkpoint(window):
        by_handle = {w['handle']:i for i,w in enumerate(result['windows'])}
        if window['handle'] in by_handle:
            result['windows'][by_handle[window['handle']]] = window
        else:
            result['windows'].append(window)
        result['assessment'] = assess_windows(result['windows'])
        if on_progress:
            on_progress(result)
    try:
        from .windows_diagnostics import collect_windows
        observed = collect_windows(include_names,on_window=checkpoint)
        result['windows'] = observed['windows']
        result['scan'] = observed['scan']
        if observed['scan']['truncated']:
            result['warnings'].append('达到检测时间或数量上限，当前结构可能不完整。')
    except Exception as exc:
        result['warnings'].append('Windows 只读检测出现错误：'+type(exc).__name__)
    result['assessment'] = assess_windows(result['windows'])
    result['warnings'].append(result['assessment']['next_action'])
    result['warnings'].append('仍需验证店铺/会话/消息身份、人工草稿和发送确认；真实发送未开放。')
    return result


def summarize(report):
    if report['live_ready']:
        return '接入检查完成'
    return '未验证千牛真实收发：' + '；'.join(report.get('warnings',[]))


def save_report(path, report):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
