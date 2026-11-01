"""诊断进程监督：界面和 bat 启动都有限时，卡住时保留已采集结构。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def supervise(command, output, timeout=25, env=None):
    timed_out = False
    status = None
    flags = {'creationflags':0x08000000} if sys.platform == 'win32' else {}
    try:
        completed = subprocess.run(command,env=env,timeout=timeout,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
        status = completed.returncode
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for the child before raising.
        timed_out = True
    output = Path(output)
    try:
        if not output.is_file() or output.stat().st_size > 5_000_000:
            raise ValueError('missing or oversized report')
        report = json.loads(output.read_text(encoding='utf-8'))
        if not isinstance(report,dict) or report.get('report_version') != 2:
            raise ValueError('invalid report format')
    except (ValueError,OSError):
        raise RuntimeError('检测未产生有效报告，请确认检测依赖已安装，或检查当前程序的运行权限。') from None
    if timed_out or status != 0:
        report['timed_out'] = timed_out
        report['partial'] = True
        report['live_ready'] = False
        report.setdefault('warnings',[]).append('检测超时，已终止探针并保留部分结果。' if timed_out else '检测进程异常退出，当前为部分结果。')
        assessment = report.get('assessment',{})
        if assessment.get('status') not in ('uia_descendants_found','native_children_found'):
            assessment = dict(status='probe_incomplete',next_action='检测尚未完整结束，不能据此判断聊天控件是否存在。',live_ready=False)
        report['assessment'] = dict(assessment,partial=True)
    return report


def run_diagnostic(include_names=False):
    command = [sys.executable]
    env = os.environ.copy()
    if not getattr(sys,'frozen',False):
        command += ['-m','qianniu_assistant']
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    command += ['--diagnose-worker']
    if include_names:
        command += ['--include-names']
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'report.json'
        return supervise(command+['--output',str(output)],output,env=env)
