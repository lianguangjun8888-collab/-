from dataclasses import replace
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from qianniu_assistant.models import Rule
from qianniu_assistant.store import Store
from qianniu_assistant.ui import MainWindow, RuleDialog


def test_rule_editor_rejects_bad_rule_then_saves_roundtrip(app,tmp_path):
 s=Store(tmp_path/'x.db'); d=RuleDialog(s)
 d.name.setText('问候'); d.expression.setText('你好++您好'); d.replies.setPlainText('在的\n您好')
 d.save()
 assert d.error.text() and s.rules()==[]
 d.expression.setText('你好#您好'); d.save()
 assert s.rules()[0].replies==['在的','您好']
 e=RuleDialog(s,s.rules()[0]); e.name.setText('修改'); e.save()
 assert len(s.rules())==1 and s.rules()[0].name=='修改'


def test_rules_filter_test_preview_and_safe_live_state(app,tmp_path):
 s=Store(tmp_path/'x.db'); s.save_rule(Rule(name='问候',expression='你好#您好',replies=['在的','您好']))
 w=MainWindow(s); w.show(); app.processEvents()
 assert not w.live_start.isEnabled()
 assert '未验证' in w.connection.text()
 assert w.rule_table.rowCount()==1
 w.search.setText('找不到'); assert w.rule_table.rowCount()==0
 w.search.clear(); assert w.rule_table.rowCount()==1
 w.message.setPlainText('您好！'); w.test_rule()
 assert '在的' in w.test_output.toPlainText() and '问候' in w.test_output.toPlainText()
 assert s.cursor('模拟店铺',s.rules()[0].id)==0
 assert w.ai_model.currentText()=='qwen2.5:3b'
 assert w.fallback.currentData()=='none'
 w.close(); app.processEvents()


def test_add_button_and_settings_persist_without_enabling_live(app,tmp_path):
 s=Store(tmp_path/'x.db'); w=MainWindow(s); w.show()
 def fill():
  d=QApplication.activeModalWidget()
  assert isinstance(d,RuleDialog)
  d.name.setText('物流'); d.expression.setText('物流'); d.replies.setPlainText('我来核实')
  d.save_button.click()
 QTimer.singleShot(10,fill)
 w.add_button.click()
 assert s.rules()[0].name=='物流'
 w.fallback.setCurrentIndex(w.fallback.findData('ai'))
 w.shop_info.setPlainText('售后由人工处理'); w.save_ai_settings()
 assert Store(tmp_path/'x.db').settings()['shop_info']=='售后由人工处理'
 assert not w.live_start.isEnabled()
 w.close()


def test_editor_does_not_silently_discard_excess_replies(app,tmp_path):
 s=Store(tmp_path/'x.db'); d=RuleDialog(s)
 d.name.setText('多回复'); d.expression.setText('你好')
 d.replies.setPlainText('\n'.join(f'回复 {i}' for i in range(101)))
 d.save()
 assert s.rules()==[] and d.error.text()


def test_detect_models_can_be_retried_when_none_installed(app,tmp_path,monkeypatch):
 import time
 import httpx
 import qianniu_assistant.ui as ui
 from qianniu_assistant.ai import AIClient
 from PySide6.QtTest import QTest
 monkeypatch.setattr(ui,'AIClient',lambda **kwargs:AIClient(**kwargs,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'models':[]}))))
 w=MainWindow(Store(tmp_path/'x.db')); w.detect_models()
 deadline=time.monotonic()+3
 while w.jobs and time.monotonic()<deadline: app.processEvents(); QTest.qWait(5)
 assert not w.jobs
 w.detect_models()
 assert w.jobs, '检测模型应可再次启动，不被空模型名阻止'
 while w.jobs and time.monotonic()<deadline+3: app.processEvents(); QTest.qWait(5)
 w.close()
