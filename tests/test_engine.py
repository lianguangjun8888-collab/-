import asyncio
from dataclasses import replace
from qianniu_assistant.models import MessageEvent, Rule
from qianniu_assistant.store import Store
from qianniu_assistant.engine import Coordinator
from qianniu_assistant.adapters import SimulationAdapter, UnavailableAdapter


def setup(tmp_path):
 s=Store(tmp_path/'x.db'); a=SimulationAdapter(); c=Coordinator(s,a,ai_delay=0)
 c.enable_shop('甲',True)
 return s,a,c


def event(id='1',text='你好',conversation='客人',shop='甲',kind='buyer_text'):
 return MessageEvent(shop,conversation,id,text,kind)


def test_paused_preview_rotation_and_dedupe(tmp_path):
 async def run():
  s,a,c=setup(tmp_path); s.save_rule(Rule(name='好',expression='你好',replies=['在的','您好']))
  assert (await c.handle(event())).status=='paused'
  assert c.preview('甲','你好').reply=='在的'
  c.set_enabled(True)
  assert (await c.handle(event())).reply=='在的'
  assert (await c.handle(event())).status=='duplicate'
  assert (await c.handle(event('2'))).reply=='您好'
  assert len(a.sent)==2
 asyncio.run(run())


def test_scope_priority_disabled_and_fallback(tmp_path):
 async def run():
  s,a,c=setup(tmp_path); c.set_enabled(True)
  s.save_rule(Rule(name='general',expression='你好',replies=['通用']))
  s.save_rule(Rule(name='shop',expression='你好',replies=['专用'],shop='甲'))
  s.save_rule(Rule(name='disabled',expression='你好',replies=['错'],priority=0,enabled=False))
  assert (await c.handle(event())).reply=='专用'
  c.enable_shop('乙',True)
  assert (await c.handle(event('2',shop='乙'))).reply=='通用'
  assert (await c.handle(event('3',text='未知'))).status=='no_match'
  s.set_settings({'fallback':'default','default_reply':'稍等'})
  assert (await c.handle(event('4',text='未知'))).reply=='稍等'
  assert (await c.handle(event('5',kind='image'))).status=='ignored'
 asyncio.run(run())


def test_unknown_send_pauses_conversation_without_rotation(tmp_path):
 class Uncertain:
  async def send(self,event,text): return False
 async def run():
  s,a,c=setup(tmp_path); c.adapter=Uncertain(); c.set_enabled(True)
  r=Rule(name='x',expression='你好'); s.save_rule(r)
  assert (await c.handle(event())).status=='unconfirmed'
  assert s.cursor('甲',r.id)==0
  assert (await c.handle(event('2'))).status=='paused'
  c.resume('甲','客人'); c.adapter=a
  assert (await c.handle(event('3'))).status=='sent'
 asyncio.run(run())


def test_delayed_ai_cancelled_by_takeover_and_settings_change(tmp_path):
 class Slow:
  def __init__(self): self.started=asyncio.Event(); self.finish=asyncio.Event()
  async def reply(self,text): self.started.set(); await self.finish.wait(); return 'AI回复'
 async def run():
  s,a,c=setup(tmp_path); c.set_enabled(True); s.set_settings({'fallback':'ai'})
  slow=Slow(); c.ai=slow
  task=asyncio.create_task(c.handle(event())); await slow.started.wait()
  c.takeover('甲','客人'); slow.finish.set()
  assert (await task).status=='cancelled'; assert a.sent==[]
  c.resume('甲','客人'); slow=Slow(); c.ai=slow
  task=asyncio.create_task(c.handle(event('2'))); await slow.started.wait()
  s.set_settings({'fallback':'none'}); slow.finish.set()
  assert (await task).status=='cancelled'; assert a.sent==[]
 asyncio.run(run())


def test_new_message_invalidates_ai_but_same_text_is_distinct_event(tmp_path):
 class Slow:
  def __init__(self): self.started=asyncio.Event()
  async def reply(self,text): self.started.set(); await asyncio.sleep(60); return '旧AI'
 async def run():
  s,a,c=setup(tmp_path); c.set_enabled(True); s.set_settings({'fallback':'ai'})
  slow=Slow(); c.ai=slow
  task=asyncio.create_task(c.handle(event(text='问题'))); await slow.started.wait()
  s.save_rule(Rule(name='新消息',expression='你好',replies=['在的']))
  assert (await c.handle(event('2'))).reply=='在的'
  assert (await task).status=='cancelled'
  assert len(a.sent)==1
 asyncio.run(run())


def test_manual_message_stops_only_its_conversation(tmp_path):
 async def run():
  s,a,c=setup(tmp_path); c.set_enabled(True); s.save_rule(Rule(name='x',expression='你好'))
  await c.handle(event(kind='human_outgoing'))
  assert (await c.handle(event('2'))).status=='paused'
  assert (await c.handle(event('3',conversation='另客'))).status=='sent'
 asyncio.run(run())


def test_unavailable_adapter_cannot_claim_live_success(tmp_path):
 async def run():
  s,a,c=setup(tmp_path); c.adapter=UnavailableAdapter(); c.set_enabled(True)
  s.save_rule(Rule(name='x',expression='你好'))
  assert (await c.handle(event())).status=='error'
  assert not any(h['status']=='sent' for h in s.history())
 asyncio.run(run())
