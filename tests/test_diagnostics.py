import json
from qianniu_assistant.diagnostics import diagnose, save_report, summarize


def test_linux_is_not_misreported_as_compatible(tmp_path):
 result=diagnose()
 assert result['target_version']=='9.1907n'
 assert not result['live_ready']
 assert not result['capabilities']['message_events']
 path=tmp_path/'检查.json'; save_report(path,result)
 assert json.loads(path.read_text('utf-8'))['live_ready'] is False
 assert '未' in summarize(result) or 'Windows' in summarize(result)


def test_diagnostic_child_writes_utf8_report_without_stdout(tmp_path):
 import subprocess,sys,os
 from pathlib import Path
 dest=tmp_path/'诊断.json'
 env=os.environ | {'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
 proc=subprocess.run([sys.executable,'-m','qianniu_assistant','--diagnose','--output',str(dest)],env=env,capture_output=True,timeout=15)
 assert proc.returncode==0
 assert json.loads(dest.read_text('utf-8'))['live_ready'] is False
 assert proc.stdout==b''
