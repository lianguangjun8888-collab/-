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


def test_v3_checkpoints_do_not_duplicate_windows_or_claim_readiness(monkeypatch):
 from copy import deepcopy
 from types import SimpleNamespace
 import qianniu_assistant.diagnostics as diagnostic
 import qianniu_assistant.windows_diagnostics as native
 monkeypatch.setattr(diagnostic,'sys',SimpleNamespace(platform='win32'))
 def collect(include_names,on_window):
  entry={'handle':1,'visible':True,'minimized':False,'uia_raw':{'controls':[]},'native_children':{'controls':[]}}
  on_window(entry)
  entry['uia_raw']['controls']=[{'depth':0},{'depth':1}]
  on_window(entry)
  return {'windows':[entry],'scan':{'truncated':False}}
 monkeypatch.setattr(native,'collect_windows',collect)
 saved=[]
 report=diagnostic.diagnose(on_progress=lambda data:saved.append(deepcopy(data)))
 assert report['report_version']==3
 assert report['assessment']['status']=='uia_descendants_found'
 assert not report['live_ready'] and not report['version_verified']
 assert len(report['windows'])==1
 assert saved[0]['windows']==[]
 assert len(saved[-1]['windows'])==1


def test_provider_failure_still_keeps_partial_window_metadata(monkeypatch):
 from types import SimpleNamespace
 import qianniu_assistant.diagnostics as diagnostic
 import qianniu_assistant.windows_diagnostics as native
 monkeypatch.setattr(diagnostic,'sys',SimpleNamespace(platform='win32'))
 def collect(include_names,on_window):
  on_window({'handle':1,'visible':True,'minimized':False,'uia_raw':{'controls':[]},'native_children':{'controls':[]}})
  raise RuntimeError('private body')
 monkeypatch.setattr(native,'collect_windows',collect)
 report=diagnostic.diagnose()
 assert len(report['windows'])==1
 assert 'private body' not in str(report)
 assert report['warnings'] and not report['live_ready']
