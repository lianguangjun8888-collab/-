"""有界的结构采集和报告解释，不读取消息内容或推断收发就绪。"""
from collections import deque
import time


def collect_tree(root, children, describe, max_nodes=400, max_depth=6, with_paths=False, deadline=None):
    queue = deque([(root,0,[])])
    result = dict(controls=[],errors=[],truncated=False,depth_limit_reached=False,time_limit_reached=False)
    while queue and len(result['controls']) < max_nodes:
        if deadline is not None and time.monotonic() >= deadline:
            result['time_limit_reached'] = result['truncated'] = True
            break
        node, depth, path = queue.popleft()
        try:
            entry = describe(node,depth)
            if with_paths:
                entry = dict(entry,path=path)
            result['controls'].append(entry)
        except Exception as exc:
            result['errors'].append(dict(stage='properties',depth=depth,error_type=type(exc).__name__))
            # Still bound work when a provider returns only unreadable nodes.
            if len(result['errors']) >= max_nodes:
                result['truncated'] = True
                break
        if depth >= max_depth:
            result['depth_limit_reached'] = True
            try:
                sentinel = object()
                result['truncated'] = result['truncated'] or next(iter(children(node)),sentinel) is not sentinel
            except Exception as exc:
                result['errors'].append(dict(stage='children',depth=depth,error_type=type(exc).__name__))
                result['truncated'] = True
            continue
        try:
            for index, child in enumerate(children(node)):
                if deadline is not None and time.monotonic() >= deadline:
                    result['time_limit_reached'] = result['truncated'] = True
                    break
                if index >= 100 or len(queue) >= max_nodes:
                    result['truncated'] = True
                    break
                queue.append((child,depth+1,path+[index]))
        except Exception as exc:
            result['errors'].append(dict(stage='children',depth=depth,error_type=type(exc).__name__))
    result['truncated'] = bool(queue) or result['truncated']
    return result


def assess_windows(windows):
    active = [w for w in windows if w.get('visible') and not w.get('minimized')]
    observations = [w.get('uia_raw',{}) for w in active]
    observations += [r.get('uia_raw',{}) for w in active for r in w.get('renderers',[])]
    if not windows:
        status, action = 'no_windows','请启动千牛并打开客服接待窗口，再运行检测。'
    elif not active:
        status, action = 'no_visible_chat_window','请将千牛客服接待窗口恢复并打开一个买家会话，保持窗口可见后再检测。'
    elif any(observation.get('input_candidates') for observation in observations):
        status, action = 'input_candidates_found','发现编辑控件候选；还需确认其所属会话、消息区和发送操作，不能直接开启自动回复。'
    elif any(len(observation.get('controls',[])) > 1 for observation in observations):
        status, action = 'uia_descendants_found','已取得原始控件结构；还需验证店铺、会话、消息方向和稳定标识，不能直接启用发送。'
    elif any(w.get('native_children',{}).get('controls') for w in active):
        status, action = 'native_children_found','发现原生子窗口，但还需确定聊天区域的访问方式；真实发送保持关闭。'
    elif any(observation.get('errors') for observation in observations):
        status, action = 'provider_error','辅助功能接口返回读取错误，不等于窗口没有子控件；请检查报告中的权限和错误类型。'
    elif any(observation.get('status') in ('not_run','skipped_budget') or not observation.get('controls') or observation.get('truncated') for observation in observations):
        status, action = 'probe_incomplete','原始控件接口尚未完成读取，当前不能判断是否只有窗口外框。'
    elif any(w.get('native_children',{}).get('errors') for w in active):
        status, action = 'native_probe_error','原生子窗口枚举出现错误，不能把读取失败当作没有子窗口；请查看错误类型和权限状态。'
    else:
        status, action = 'root_only','仍只读取到窗口外框；请确认已打开客服接待中的买家会话。若状态无变化，当前接口不足以可靠自动回复。'
    return dict(status=status,next_action=action,live_ready=False)
