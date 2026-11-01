import json
from pathlib import Path
import subprocess
import sys
from qianniu_assistant.diagnostic_runner import supervise


def test_hung_probe_preserves_checkpoint_and_is_terminated(tmp_path):
 output=tmp_path/'report.json'
 script="import json,time,pathlib; pathlib.Path(__import__('sys').argv[1]).write_text(json.dumps({'report_version':2,'live_ready':False,'windows':[{'handle':1}],'warnings':[]})); time.sleep(30)"
 report=supervise([sys.executable,'-c',script,str(output)],output,timeout=1)
 assert report['timed_out'] is True
 assert report['assessment']['status']=='probe_incomplete'
 assert report['windows']==[{'handle':1}]
 assert not report['live_ready']
 assert report['warnings']


def test_completed_probe_report_remains_complete(tmp_path):
 output=tmp_path/'report.json'
 script="import json,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({'report_version':2,'live_ready':False,'windows':[],'warnings':[]}))"
 report=supervise([sys.executable,'-c',script,str(output)],output,timeout=5)
 assert not report.get('timed_out') and not report['live_ready']


def test_bad_probe_is_not_reported_as_success(tmp_path):
 import pytest
 with pytest.raises(RuntimeError): supervise([sys.executable,'-c','raise SystemExit(2)'],tmp_path/'missing.json',timeout=5)
