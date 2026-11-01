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


def prioritize_windows(handles, is_visible, is_minimized):
    def rank(handle):
        try:
            return (not bool(is_visible(handle)),bool(is_minimized(handle)))
        except Exception:
            return (True,True)
    return sorted(handles,key=rank)


def select_renderers(controls, limit=4):
    unique = {}
    for node in controls:
        if node.get('class_name') != 'Chrome_RenderWidgetHostHWND' or not node.get('visible'):
            continue
        rect = node.get('rect',[])
        if len(rect) != 4 or rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        unique.setdefault(node['handle'],node)
    return sorted(unique.values(),key=lambda n:(n['rect'][2]-n['rect'][0])*(n['rect'][3]-n['rect'][1]),reverse=True)[:limit]


def describe_element(element, ui, depth, include_names):
    result = dict(depth=depth,control_type=ui.known_control_type_ids.get(element.CurrentControlType,'Unknown'),
                  class_name=(element.CurrentClassName or '')[:256],automation_id=(element.CurrentAutomationId or '')[:256],
                  framework_id=(element.CurrentFrameworkId or '')[:80],offscreen=bool(element.CurrentIsOffscreen))
    for key, attribute in [('native_handle','CurrentNativeWindowHandle'),('process_id','CurrentProcessId'),('is_password','CurrentIsPassword')]:
        try:
            result[key] = getattr(element,attribute)
            if key == 'is_password' and result[key] is not None:
                result[key] = bool(result[key])
        except Exception:
            result[key] = None
    try:
        result['runtime_id'] = list(element.GetRuntimeId() or [])[:32]
    except Exception:
        result['runtime_id'] = None
    try:
        rect = element.CurrentBoundingRectangle
        result['rect'] = [rect.left,rect.top,rect.right,rect.bottom]
    except Exception:
        result['rect'] = None
    patterns = {}
    for name in ('Value','Text','Invoke','LegacyIAccessible'):
        try:
            prop = getattr(ui.UIA_dll,'UIA_Is'+name+'PatternAvailablePropertyId')
            patterns[name] = bool(element.GetCurrentPropertyValue(prop))
        except Exception:
            patterns[name] = None
    result['patterns_available'] = patterns
    if include_names and result['is_password'] is not True:
        result['name'] = (element.CurrentName or '')[:300]
    return result


def _raw_tree(hwnd, include_names, max_nodes=400, max_depth=8, targeted=False, deadline=None, on_progress=None):
    from pywinauto.uia_defines import IUIA
    ui = IUIA()
    walker = ui.iuia.RawViewWalker
    root = ui.iuia.ElementFromHandle(hwnd)
    candidates = dict(input_candidates=[],button_candidates=[],candidate_errors=[])
    if targeted:
        # Search editable controls before traversing long chat history, so a
        # large history subtree cannot exhaust the budget before the editor.
        for kind, destination in [('Edit','input_candidates'),('Button','button_candidates')]:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                condition = ui.iuia.CreatePropertyCondition(ui.UIA_dll.UIA_ControlTypePropertyId,ui.known_control_types[kind])
                elements = root.FindAll(ui.tree_scope['descendants'],condition)
                for i in range(min(elements.Length,100)):
                    if deadline is not None and time.monotonic() >= deadline:
                        candidates[destination+'_truncated'] = True
                        break
                    node = describe_element(elements.GetElement(i),ui,None,include_names)
                    if node['is_password'] is not True and not node['offscreen']:
                        candidates[destination].append(node)
                if elements.Length > 100:
                    candidates[destination+'_truncated'] = True
            except Exception as exc:
                candidates['candidate_errors'].append(dict(control_type=kind,error_type=type(exc).__name__))
            if on_progress:
                on_progress(dict(candidates,controls=[],errors=[],status='collecting'))
    def children(element):
        child = walker.GetFirstChildElement(element)
        count = 0
        while child and count < 101:
            yield child
            child = walker.GetNextSiblingElement(child)
            count += 1
    tree = collect_tree(root,children,lambda e,d:describe_element(e,ui,d,include_names),
                        max_nodes=max_nodes,max_depth=max_depth,with_paths=True,deadline=deadline)
    return dict(tree,**candidates)


def collect_windows(include_names=False, on_window=None, max_seconds=18):
    import win32api
    import win32gui
    import win32process
    import win32security
    started = time.monotonic()
    deadline = started + max_seconds
    cache = {}
    windows = []
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    handles = []
    scanned = 0
    truncated = False
    renderer_budget = 6
    renderers_scanned = 0
    win32gui.EnumWindows(lambda h,_:handles.append(h) or True,None)
    handles = prioritize_windows(handles,win32gui.IsWindowVisible,win32gui.IsIconic)
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
                         renderers=[],uia_raw=dict(controls=[],errors=[],status='not_run'))
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
            if entry['visible'] and not entry['minimized']:
                try:
                    win32gui.EnumChildWindows(hwnd,native,None)
                except Exception as exc:
                    if not entry['native_children']['truncated']:
                        entry['native_children']['errors'].append(dict(error_type=type(exc).__name__))
            else:
                entry['native_children']['status'] = 'skipped_hidden_or_minimized'
            # Save native progress before querying a possibly unresponsive provider.
            if on_window:
                on_window(entry)
            if not entry['visible'] or entry['minimized']:
                entry['uia_raw']['status'] = 'skipped_hidden_or_minimized'
            else:
                # Probe large, visible Chromium renderers directly. Do not
                # spend the depth allowance climbing through the Qt shell.
                for renderer in select_renderers(entry['native_children']['controls']):
                    if renderer_budget <= 0 or time.monotonic() >= deadline:
                        entry['renderers_truncated'] = True
                        truncated = True
                        break
                    renderer_budget -= 1
                    renderers_scanned += 1
                    probe = dict(handle=renderer['handle'],rect=renderer['rect'],
                                 uia_raw=dict(status='not_run',controls=[],errors=[]))
                    entry['renderers'].append(probe)
                    if on_window:
                        on_window(entry)
                    def progress(data, probe=probe):
                        probe['uia_raw'] = data
                        if on_window:
                            on_window(entry)
                    try:
                        win32gui.SendMessageTimeout(renderer['handle'],0x003D,0,-25,0x0003,1000)
                    except Exception as exc:
                        probe['accessibility_request'] = type(exc).__name__
                    try:
                        probe['uia_raw'] = dict(_raw_tree(renderer['handle'],include_names,max_nodes=1200,max_depth=32,
                            targeted=True,deadline=min(deadline,time.monotonic()+5),on_progress=progress),status='completed')
                    except Exception as exc:
                        probe['uia_raw'] = dict(status='failed',controls=[],errors=[dict(stage='root',error_type=type(exc).__name__)])
                    if on_window:
                        on_window(entry)
                if time.monotonic() >= deadline:
                    entry['uia_raw']['status'] = 'skipped_budget'
                    truncated = True
                    if on_window:
                        on_window(entry)
                    continue
                try:
                    # UiaRootObjectId=-25. SMTO_ABORTIFHUNG|SMTO_BLOCK, 1 second.
                    win32gui.SendMessageTimeout(hwnd,0x003D,0,-25,0x0003,1000)
                    entry['accessibility_request'] = 'completed'
                except Exception as exc:
                    entry['accessibility_request'] = type(exc).__name__
                try:
                    entry['uia_raw'] = dict(_raw_tree(hwnd,include_names,deadline=deadline),status='completed')
                except Exception as exc:
                    entry['uia_raw'] = dict(controls=[],errors=[dict(stage='root',error_type=type(exc).__name__)],status='failed')
            if on_window:
                on_window(entry)
        except Exception:
            # Inaccessible unrelated windows must not abort the whole inventory.
            continue
    return dict(windows=windows,scan=dict(windows_scanned=scanned,truncated=truncated or len(handles)>1000,
                                        renderer_roots_scanned=renderers_scanned,
                                        elapsed_seconds=round(time.monotonic()-started,2)))
