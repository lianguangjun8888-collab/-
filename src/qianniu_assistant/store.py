"""本地 SQLite 持久化；规则导入和发送确认分别保持原子性。"""
from dataclasses import asdict
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from .models import Rule
from .matching import validate_rule

DEFAULTS = dict(fallback='none', default_reply='您好，稍后由人工为您处理。',
                simple_mode=False, simple_reply='您好，请稍等。', ai_provider='ollama',
                model='qwen2.5:3b', base_url='http://127.0.0.1:11434', shop_info='', shop_infos={},
                record_body=True)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              shop TEXT, conversation TEXT, event_id TEXT, created TEXT NOT NULL,
              PRIMARY KEY(shop, conversation, event_id));
            CREATE TABLE IF NOT EXISTS cursors (
              shop TEXT, rule_id TEXT, position INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(shop, rule_id));
            CREATE TABLE IF NOT EXISTS history (
              id INTEGER PRIMARY KEY, shop TEXT, conversation TEXT, event_id TEXT,
              message TEXT, reply TEXT, status TEXT, rule_id TEXT, created TEXT,
              UNIQUE(shop, conversation, event_id));
            ''')
            cutoff = (datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
            db.execute('DELETE FROM history WHERE created < ?', (cutoff,))
            db.execute('DELETE FROM events WHERE created < ?', (cutoff,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_rule(self, rule):
        validate_rule(rule)
        with self.connect() as db:
            db.execute('INSERT INTO rules VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                       (rule.id, json.dumps(asdict(rule), ensure_ascii=False)))

    def delete_rule(self, rule_id):
        with self.connect() as db:
            db.execute('DELETE FROM rules WHERE id=?', (rule_id,))
            db.execute('DELETE FROM cursors WHERE rule_id=?', (rule_id,))

    def rules(self, shop=None):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM rules ORDER BY rowid').fetchall()
        rules = [Rule(**json.loads(r['body'])) for r in rows]
        if shop is not None:
            rules = [r for r in rules if r.shop in ('', shop)]
        return sorted(rules, key=lambda r: (r.priority, r.shop == '' if shop else False))

    def export_rules(self, path):
        payload = dict(version=1, rules=[asdict(r) for r in self.rules()])
        dest = Path(path)
        temp = dest.with_name(dest.name + '.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(dest)

    def import_rules(self, path):
        path = Path(path)
        if path.stat().st_size > 5_000_000:
            raise ValueError('导入文件不能超过 5 MB')
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('rules'), list):
                raise ValueError('规则文件格式或版本不正确')
            if len(data['rules']) > 5000:
                raise ValueError('最多导入 5000 条规则')
            rules = [Rule(**row) for row in data['rules']]
            ids = [r.id for r in rules]
            if len(ids) != len(set(ids)):
                raise ValueError('文件中有重复规则标识')
            for r in rules:
                validate_rule(r)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError('规则文件格式不正确') from exc
        with self.connect() as db:
            for r in rules:
                db.execute('INSERT INTO rules VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                           (r.id, json.dumps(asdict(r), ensure_ascii=False)))
        return len(rules)

    def settings(self):
        with self.connect() as db:
            return deepcopy(DEFAULTS) | {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}

    def set_settings(self, values):
        if set(values) - DEFAULTS.keys():
            raise ValueError('包含不支持的设置；不存储密钥')
        for k, v in values.items():
            if type(v) is not type(DEFAULTS[k]):
                raise ValueError(f'{k} 类型不正确')
            if isinstance(v, str) and len(v) > 10000:
                raise ValueError('设置文本过长')
            if k == 'shop_infos' and (len(v) > 100 or any(not isinstance(shop,str) or not shop.strip()
                    or len(shop) > 200 or not isinstance(info,str) or len(info) > 10000 for shop,info in v.items())):
                raise ValueError('店铺资料须为店铺名到文本的映射，最多 100 店，每店 10000 字')
        if values.get('fallback', 'none') not in ('none', 'default', 'ai'):
            raise ValueError('未知未命中策略')
        if values.get('ai_provider', 'ollama') != 'ollama':
            raise ValueError('自用免费版仅使用本地 Ollama')
        if any(k in values for k in ('base_url', 'model')):
            from .ai import AIClient
            cfg = self.settings() | values
            AIClient(model=cfg['model'], base_url=cfg['base_url'])
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',
                           [(k, json.dumps(v, ensure_ascii=False)) for k, v in values.items()])

    def claim(self, shop, conversation, event_id):
        if not all((shop.strip(), conversation.strip(), event_id.strip())):
            raise ValueError('消息须有店铺、会话及事件标识')
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?)',
                             (shop, conversation, event_id, datetime.now(timezone.utc).isoformat()))
            return cur.rowcount == 1

    def cursor(self, shop, rule_id):
        with self.connect() as db:
            row = db.execute('SELECT position FROM cursors WHERE shop=? AND rule_id=?', (shop,rule_id)).fetchone()
        return row[0] if row else 0

    def record(self, shop, conversation, event_id, message, reply, status, rule_id=''):
        keep = self.settings()['record_body']
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO history (shop,conversation,event_id,message,reply,status,rule_id,created) VALUES (?,?,?,?,?,?,?,?)',
                             (shop,conversation,event_id,message if keep else '',reply if keep else '',status,rule_id,datetime.now(timezone.utc).isoformat()))
            if cur.rowcount and status == 'sent' and rule_id:
                db.execute('INSERT INTO cursors VALUES (?,?,1) ON CONFLICT(shop,rule_id) DO UPDATE SET position=position+1', (shop,rule_id))

    def history(self, limit=500):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM history ORDER BY id DESC LIMIT ?', (limit,))]

    def clear_history(self):
        with self.connect() as db:
            db.execute('DELETE FROM history')
