"""话术预览和有状态回复调度；所有真实收发仍需平台适配。"""
import asyncio
from dataclasses import dataclass, field
from .matching import evaluate, normalize
from .models import MessageEvent


@dataclass
class Outcome:
    status: str
    reply: str = ''
    rule_id: str = ''
    name: str = ''
    groups: list[str] = field(default_factory=list)
    normalized: str = ''


class Coordinator:
    def __init__(self, store, adapter, ai=None, ai_delay=1.0):
        self.store, self.adapter, self.ai = store, adapter, ai
        self.ai_delay = ai_delay
        self.enabled = False
        self.shops = set()
        self.paused = set()
        self.epoch = 0
        self.revisions = {}
        self.controls = {}
        self.ai_tasks = {}
        self.pending = {}
        self.locks = {}

    def set_enabled(self, value):
        self.enabled = bool(value)
        self.epoch += 1
        if not value:
            for t in self.ai_tasks.values():
                t.cancel()
            self.pending.clear()

    def enable_shop(self, shop, value):
        if value:
            self.shops.add(shop)
        else:
            self.shops.discard(shop)
        self.epoch += 1

    def takeover(self, shop, conversation):
        key = (shop, conversation)
        self.paused.add(key)
        self.controls[key] = self.controls.get(key, 0) + 1
        if key in self.ai_tasks:
            self.ai_tasks[key].cancel()
        self.pending.pop(key, None)

    def resume(self, shop, conversation):
        key = (shop, conversation)
        self.paused.discard(key)
        self.controls[key] = self.controls.get(key, 0) + 1

    def _gate(self, event):
        return self.epoch, self.controls.get((event.shop,event.conversation), 0)

    def _allowed(self, event, gate):
        return (self.enabled and event.shop in self.shops and
                (event.shop,event.conversation) not in self.paused and self._gate(event) == gate)

    def preview(self, shop, text):
        cfg = self.store.settings()
        if not normalize(text).strip():
            return Outcome('no_match', normalized=normalize(text))
        if cfg['simple_mode']:
            return Outcome('preview',cfg['simple_reply'],name='统一话术',normalized=normalize(text))
        for rule in self.store.rules(shop):
            if not rule.enabled:
                continue
            match = evaluate(rule.expression, text, rule.match_type)
            if match.matched:
                cursor = self.store.cursor(shop,rule.id)
                return Outcome('preview',rule.replies[cursor % len(rule.replies)],rule.id,rule.name,match.groups,match.normalized)
        if cfg['fallback'] == 'default':
            return Outcome('preview',cfg['default_reply'],name='默认回复',normalized=normalize(text))
        return Outcome('ai_needed' if cfg['fallback'] == 'ai' else 'no_match',normalized=normalize(text))

    def _record(self, event, outcome):
        self.store.record(event.shop,event.conversation,event.event_id,event.text,outcome.reply,outcome.status,outcome.rule_id)
        return outcome

    async def handle(self, event: MessageEvent):
        key = (event.shop,event.conversation)
        if event.kind == 'human_outgoing':
            self.takeover(*key)
            return Outcome('paused')
        if event.kind != 'buyer_text' or not normalize(event.text).strip():
            return Outcome('ignored')
        gate = self._gate(event)
        if not self._allowed(event,gate):
            return Outcome('paused')
        if not self.store.claim(event.shop,event.conversation,event.event_id):
            return Outcome('duplicate')
        revision = self.revisions[key] = self.revisions.get(key,0) + 1
        old = self.ai_tasks.get(key)
        if old:
            old.cancel()
        self.pending.setdefault(key,[]).append(event.text)
        self.pending[key] = self.pending[key][-10:]
        settings = self.store.settings()
        rules = self.store.rules()
        result = self.preview(event.shop,event.text)
        ai_result = result.status == 'ai_needed'
        if ai_result:
            async def generate():
                await asyncio.sleep(self.ai_delay)
                ai = self.ai
                if ai is None:
                    from .ai import AIClient
                    ai = AIClient(model=settings['model'],shop_info=settings['shop_info'],base_url=settings['base_url'])
                return await ai.reply('\n'.join(self.pending.get(key, [event.text]))[-4000:])
            task = asyncio.create_task(generate())
            self.ai_tasks[key] = task
            try:
                answer = await task
                if not isinstance(answer,str) or not answer.strip():
                    return self._record(event,Outcome('error'))
                result = Outcome('preview',answer,name='本地 AI')
            except asyncio.CancelledError:
                return self._record(event,Outcome('cancelled'))
            except Exception:
                return self._record(event,Outcome('error'))
            finally:
                if self.ai_tasks.get(key) is task:
                    del self.ai_tasks[key]
        elif result.status == 'no_match':
            return self._record(event,result)
        lock = self.locks.setdefault(event.shop,asyncio.Lock())
        async with lock:
            if (not self._allowed(event,gate) or settings != self.store.settings() or rules != self.store.rules()
                    or (ai_result and self.revisions[key] != revision)):
                return self._record(event,Outcome('cancelled'))
            if not ai_result:
                # Compute rotation again under the shop send lock.
                result = self.preview(event.shop,event.text)
            if not result.reply.strip():
                return self._record(event,Outcome('no_match'))
            try:
                confirmed = await self.adapter.send(event,result.reply)
            except Exception:
                self.takeover(*key)
                return self._record(event,Outcome('error',result.reply,result.rule_id,result.name))
            result.status = 'sent' if confirmed else 'unconfirmed'
            if not confirmed:
                self.takeover(*key)
            else:
                self.pending.pop(key,None)
            return self._record(event,result)
