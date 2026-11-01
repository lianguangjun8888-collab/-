"""Windows 只读探针：原生子窗口、UIA RawView、权限与固定版本资源。

Qt 5.15.2 官方 UIA 后端在 WM_GETOBJECT 时激活 accessibility。
此处只请求标准 UIA provider，不点击、输入、读取 Value/Text 内容或修改客户端。
"""
import ctypes
from pathlib import Path
import time
from .diagnostic_tree import collect_tree


def matches_target(filename):
    return filename.casefold() in ('aliworkbench.exe','qianniu.exe','千牛.exe')


def _versions(api, exe):
    result = {}
    try:
        for lang, page in api.GetFileVersionInfo(exe,'\\VarFileInfo\\Translation'):
            for key in ('FileVersion','ProductVersion'):
                try:
                    result[key] = api.GetFileVersionInfo(exe,f'\\StringFileInfo\\{lang:04x}{page:04x}\\{key}')
                except Exception:
                    pass
    except Exception:
        pass
    try:
        fixed = api.GetFileVersionInfo(exe,'\\')
        for label in ('FileVersion','ProductVersion'):
            high, low = fixed[label+'MS'], fixed[label+'LS']
            result[label+'Numeric'] = '.'.join(str(n) for n in (high >> 16,high & 65535,low >> 16,low & 65535))
    except Exception:
        pass
    return result


def _raw_tree(hwnd, include_names):
    from pywinauto.uia_defines import IUIA
    ui = IUIA()
    walker = ui.iuia.RawViewWalker
    root = ui.iuia.ElementFromHandle(hwnd)
    def children(element):
        child = walker.GetFirstChildElement(element)
        count = 0
        while child and count < 101:
            yield child
            child = walker.GetNextSiblingElement(child)
            count += 1
    def describe(element, depth):
        result = dict(depth=depth,control_type=ui.known_control_type_ids.get(element.CurrentControlType,'Unknown'),
                      class_name=element.CurrentClassName or '',automation_id=element.CurrentAutomationId or '',
                      framework_id=element.CurrentFrameworkId or '',offscreen=bool(element.CurrentIsOffscreen))
        patterns = {}
        for name in ('Value','Text','Invoke','LegacyIAccessible'):
            try:
                prop = getattr(ui.UIA_dll,'UIA_Is'+name+'PatternAvailablePropertyId')
                patterns[name] = bool(element.GetCurrentPropertyValue(prop))
            except Exception:
                patterns[name] = None
        result['patterns_available'] = patterns
        if include_names:
            result['name'] = (element.CurrentName or '')[:300]
        return result
    return collect_tree(root,children,describe)


def collect_windows(include_names=False, on_window=None, max_seconds=18):
    import win32api
    import win32gui
    import win32process
    import win32security
    started = time.monotonic()
    cache = {}
    windows = []
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    handles = []
    scanned = 0
    truncated = False
    win32gui.EnumWindows(lambda h,_:handles.append(h) or True,None)
    for hwnd in handles[:1000]:
        if time.monotonic()-started > max_seconds or len(windows) >= 20:
            truncated = True
            break
        scanned += 1
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in cache:
                process = win32api.OpenProcess(0x410,False,pid)
                try:
                    exe = win32process.GetModuleFileNameEx(process,0)
                    name = Path(exe).name
                    if not matches_target(name):
                        cache[pid] = None
                        continue
                    info = dict(pid=pid,executable=name,versions=_versions(win32api,exe),target_elevated=None)
                    try:
                        token = win32security.OpenProcessToken(process,0x0008)
                        try:
                            info['target_elevated'] = bool(win32security.GetTokenInformation(token,win32security.TokenElevation))
                        finally:
                            token.Close()
                    except Exception:
                        pass
                    cache[pid] = info
                finally:
                    process.Close()
            if cache[pid] is None:
                continue
            entry = dict(cache[pid],handle=int(hwnd),visible=bool(win32gui.IsWindowVisible(hwnd)),
                         minimized=bool(win32gui.IsIconic(hwnd)),inspector_elevated=admin,
                         native_children=dict(controls=[],errors=[],truncated=False),
                         uia_raw=dict(controls=[],errors=[],status='not_run'))
            windows.append(entry)
            def native(child,_):
                result = entry['native_children']
                if len(result['controls']) >= 400:
                    result['truncated'] = True
                    return False
                try:
                    node = dict(handle=int(child),parent=int(win32gui.GetParent(child)),
                                class_name=win32gui.GetClassName(child),visible=bool(win32gui.IsWindowVisible(child)),
                                enabled=bool(win32gui.IsWindowEnabled(child)),rect=list(win32gui.GetWindowRect(child)))
                    if include_names:
                        node['name'] = win32gui.GetWindowText(child)[:300]
                    result['controls'].append(node)
                except Exception as exc:
                    result['errors'].append(dict(error_type=type(exc).__name__))
                return True
            try:
                win32gui.EnumChildWindows(hwnd,native,None)
            except Exception as exc:
                if not entry['native_children']['truncated']:
                    entry['native_children']['errors'].append(dict(error_type=type(exc).__name__))
            # Save native progress before querying a possibly unresponsive provider.
            if on_window:
                on_window(entry)
            if not entry['visible'] or entry['minimized']:
                entry['uia_raw']['status'] = 'skipped_hidden_or_minimized'
            else:
                try:
                    # UiaRootObjectId=-25. SMTO_ABORTIFHUNG|SMTO_BLOCK, 1 second.
                    win32gui.SendMessageTimeout(hwnd,0x003D,0,-25,0x0003,1000)
                    entry['accessibility_request'] = 'completed'
                except Exception as exc:
                    entry['accessibility_request'] = type(exc).__name__
                try:
                    entry['uia_raw'] = dict(_raw_tree(hwnd,include_names),status='completed')
                except Exception as exc:
                    entry['uia_raw'] = dict(controls=[],errors=[dict(stage='root',error_type=type(exc).__name__)],status='failed')
            if on_window:
                on_window(entry)
        except Exception:
            # Inaccessible unrelated windows must not abort the whole inventory.
            continue
    return dict(windows=windows,scan=dict(windows_scanned=scanned,truncated=truncated or len(handles)>1000,
                                        elapsed_seconds=round(time.monotonic()-started,2)))
