import json
from dataclasses import replace
import pytest
from qianniu_assistant.models import Rule
from qianniu_assistant.store import Store


def test_rule_roundtrip_and_shop_order(tmp_path):
 s=Store(tmp_path/'x.db')
 general=Rule(name='通用',expression='你好',priority=88)
 special=Rule(name='店铺',expression='你好',shop='甲',priority=88)
 disabled=Rule(name='禁用',expression='你好',enabled=False,priority=1)
 for r in [general,special,disabled]: s.save_rule(r)
 assert [r.name for r in s.rules('甲')]==['禁用','店铺','通用']
 assert [r.name for r in s.rules('乙')]==['禁用','通用']
 s.save_rule(replace(general,name='修改'))
 assert len(s.rules())==3
 s.delete_rule(special.id)
 assert len(Store(tmp_path/'x.db').rules())==2


def test_import_export_is_transactional_and_preserves_unicode(tmp_path):
 s=Store(tmp_path/'x.db'); r=Rule(name='你好',expression='您好',replies=['在的'])
 s.save_rule(r); dest=tmp_path/'rules.json'; s.export_rules(dest)
 assert '你好' in dest.read_text('utf-8')
 t=Store(tmp_path/'y.db'); assert t.import_rules(dest)==1
 assert t.rules()[0].replies==['在的']
 data=json.loads(dest.read_text()); data['rules'].append({**data['rules'][0],'id':'other','expression':'a++b'})
 dest.write_text(json.dumps(data))
 with pytest.raises(ValueError): t.import_rules(dest)
 assert len(t.rules())==1
 data['rules'][1]=data['rules'][0]; dest.write_text(json.dumps(data))
 with pytest.raises(ValueError): t.import_rules(dest)
 assert len(t.rules())==1


def test_settings_reject_secrets_and_start_paused(tmp_path):
 s=Store(tmp_path/'x.db')
 assert s.settings()['fallback']=='none'
 assert s.settings()['ai_provider']=='ollama'
 with pytest.raises(ValueError): s.set_settings({'api_key':'secret'})
 s.set_settings({'fallback':'ai','shop_info':'自家商品'})
 assert Store(tmp_path/'x.db').settings()['shop_info']=='自家商品'
 with pytest.raises(ValueError): s.set_settings({'fallback':'paid'})


def test_rotation_and_event_audit_are_atomic(tmp_path):
 s=Store(tmp_path/'x.db'); r=Rule(name='问候',expression='好'); s.save_rule(r)
 assert s.claim('店','会话','e1')
 assert not s.claim('店','会话','e1')
 assert s.claim('店','其他','e1')
 s.record('店','会话','e1','你好','在的','sent',r.id)
 assert s.cursor('店',r.id)==1
 assert s.cursor('别店',r.id)==0
 assert Store(tmp_path/'x.db').history()[0]['reply']=='在的'
 s.record('店','会话','e1','你好','在的','sent',r.id)
 assert s.cursor('店',r.id)==1
 s.set_settings({'record_body':False})
 s.record('店','会话','e2','私密消息','私密回复','error')
 assert s.history()[0]['message']=='' and s.history()[0]['reply']==''
 s.clear_history(); assert s.history()==[]
 # Clearing display history must not allow a duplicate auto-reply.
 assert not s.claim('店','会话','e1')


def test_invalid_settings_are_atomic(tmp_path):
 s=Store(tmp_path/'x.db')
 with pytest.raises(ValueError): s.set_settings({'shop_info':'changed','record_body':'false'})
 assert s.settings()['shop_info']==''


def test_shop_ai_profiles_are_isolated_and_validated(tmp_path):
 s=Store(tmp_path/'a.db'); t=Store(tmp_path/'b.db')
 s.set_settings({'shop_infos':{'甲':'甲店商品','乙':'乙店商品'}})
 assert t.settings()['shop_infos']=={}
 assert s.settings()['shop_infos']['乙']=='乙店商品'
 with pytest.raises(ValueError): s.set_settings({'shop_infos':{'甲':['invalid']}})
 assert s.settings()['shop_infos']['甲']=='甲店商品'


def test_long_running_store_prunes_expired_history_without_restart(tmp_path):
 s=Store(tmp_path/'x.db'); s.record('甲','客','e','旧消息','旧回复','error')
 with s.connect() as db:
  db.execute("UPDATE history SET created='2000-01-01T00:00:00+00:00'")
 assert s.history()==[]
 with s.connect() as db:
  assert db.execute('SELECT count(*) FROM history').fetchone()[0]==0
