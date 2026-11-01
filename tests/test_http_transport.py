"""真实本机 HTTP 传输检查；服务只返回固定测试数据，不运行真实模型。"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from qianniu_assistant.ai import AIClient


def test_local_request_ignores_proxy_and_never_leaves_loopback(monkeypatch):
 calls=[]
 class Handler(BaseHTTPRequestHandler):
  def do_POST(self):
   body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   calls.append((self.path,body))
   result={'details':{'family':'qwen2'}} if self.path=='/api/show' else {'message':{'role':'assistant','content':'本地测试回复'},'done':True}
   payload=json.dumps(result).encode()
   self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
  def log_message(self,*args): pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 worker=Thread(target=server.serve_forever,daemon=True); worker.start()
 try:
  monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
  monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
  monkeypatch.setenv('ALL_PROXY','http://127.0.0.1:1')
  monkeypatch.setenv('NO_PROXY','')
  client=AIClient(base_url=f'http://127.0.0.1:{server.server_port}')
  assert asyncio.run(client.reply('测试问题'))=='本地测试回复'
  assert [p for p,b in calls]==['/api/show','/api/chat']
  assert calls[1][1]['messages'][-1]['content']=='测试问题'
 finally:
  server.shutdown(); server.server_close(); worker.join(2)
