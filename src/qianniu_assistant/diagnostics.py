"""只读 UIA 结构检测。不修改千牛，不据控件存在就宣称可收发。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys


def diagnose(include_names=False):
    result = {'target_version':'9.1907n','platform':platform.platform(),
              'python':platform.python_version(),'created':datetime.now(timezone.utc).isoformat(),
              'live_ready':False,'version_verified':False,'windows':[], 'warnings':[],
              'capabilities':dict.fromkeys(['shop_identity','conversation_identity','message_events',
                                          'direction','draft_state','send_confirmation'],False)}
    if sys.platform != 'win32':
        result['warnings'].append('当前不是 Windows，无法检测千牛。真实发送保持关闭。')
        return result
    try:
        from pywinauto import Desktop
        import win32api
        import win32process
        desktop = Desktop(backend='uia')
        windows = desktop.windows()
        for window in windows:
            try:
                pid = window.process_id()
                handle = win32api.OpenProcess(0x410,False,pid)
                try:
                    exe = win32process.GetModuleFileNameEx(handle,0)
                finally:
                    handle.Close()
                basename = Path(exe).name
                if not any(word in basename.casefold() for word in ('qianniu','aliworkbench','千牛')):
                    continue
                versions = {}
                try:
                    for lang, page in win32api.GetFileVersionInfo(exe,'\\VarFileInfo\\Translation'):
                        for key in ('FileVersion','ProductVersion'):
                            versions[key] = win32api.GetFileVersionInfo(exe,f'\\StringFileInfo\\{lang:04x}{page:04x}\\{key}')
                except Exception:
                    versions['status'] = '无法读取版本资源'
                nodes, queue = [], [(window,0)]
                while queue and len(nodes) < 400:
                    item, depth = queue.pop(0)
                    info = item.element_info
                    entry = {'depth':depth,'control_type':info.control_type,
                             'automation_id':info.automation_id,'class_name':info.class_name}
                    if include_names:
                        entry['name'] = (info.name or '')[:300]
                    nodes.append(entry)
                    if depth < 6:
                        try:
                            queue.extend((child,depth+1) for child in item.children()[:100])
                        except Exception:
                            result['warnings'].append('部分控件不可读取。')
                result['windows'].append({'pid':pid,'executable':basename,'versions':versions,
                                          'controls':nodes,'truncated':bool(queue)})
            except Exception:
                # Inaccessible unrelated windows do not establish a QianNiu failure.
                continue
        if not result['windows']:
            result['warnings'].append('未找到可访问的千牛进程窗口，请启动千牛后再检测。')
    except Exception:
        result['warnings'].append('Windows UIA 检测不可用，请检查依赖与进程权限。')
    result['warnings'].append('当前仅完成结构采集；须据实机结果验证店铺/会话/消息身份及发送确认后编写收发适配。真实发送未开放。')
    return result


def summarize(report):
    if report['live_ready']:
        return '接入检查完成'
    return '未验证千牛真实收发：' + '；'.join(report.get('warnings',[]))


def save_report(path, report):
    Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
