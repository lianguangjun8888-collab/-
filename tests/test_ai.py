import asyncio
import json
import httpx
import pytest
from qianniu_assistant.ai import AIClient, AIError


def test_ollama_request_is_local_and_contains_shop_context():
 def respond(request):
  if request.url.path=='/api/show':
   return httpx.Response(200,json={'details':{'family':'qwen2'}})
  assert str(request.url)=='http://127.0.0.1:11434/api/chat'
  body=json.loads(request.content)
  assert body['stream'] is False
  assert body['model']=='qwen2.5:3b'
  assert '包邮' in body['messages'][0]['content']
  assert body['messages'][-1]=={'role':'user','content':'什么时候发货？'}
  assert 'authorization' not in request.headers
  return httpx.Response(200,json={'model':'qwen2.5:3b','message':{'role':'assistant','content':'请稍等，我帮您核实。'},'done':True})
 client=AIClient(shop_info='本店包邮',transport=httpx.MockTransport(respond))
 assert asyncio.run(client.reply('什么时候发货？'))=='请稍等，我帮您核实。'


@pytest.mark.parametrize('url', ['https://api.openai.com','http://example.com:11434','http://127.0.0.1.evil:11434',
 'http://user:password@localhost:11434','http://localhost:11434/path','ftp://127.0.0.1','http://localhost?proxy=evil'])
def test_remote_urls_rejected(url):
 with pytest.raises(ValueError): AIClient(base_url=url)


@pytest.mark.parametrize('model',['','a b','qwen3:cloud','deepseek:671b-cloud','a'*129])
def test_invalid_or_cloud_model_rejected(model):
 with pytest.raises(ValueError): AIClient(model=model)


@pytest.mark.parametrize('status,data',[(404,{'error':'model not found'}),(500,{'error':'private user text'}),
 (200,{'message':{'content':''}}),(200,{'message':{'content':None}}),(200,{'message':{'content':['bad']}})])
def test_failures_are_safe_and_not_sent(status,data):
 client=AIClient(transport=httpx.MockTransport(lambda r:httpx.Response(status,json=data)))
 with pytest.raises(AIError) as err: asyncio.run(client.reply('private user text'))
 assert 'private user text' not in str(err.value)


def test_timeout_and_model_detection():
 def timeout(r): raise httpx.ReadTimeout('secret text',request=r)
 with pytest.raises(AIError): asyncio.run(AIClient(transport=httpx.MockTransport(timeout)).reply('问题'))
 data={'models':[{'name':'qwen2.5:3b'},{'name':'deepseek:671b-cloud','remote_host':'https://ollama.com'}, {'name':'local-but-remote','remote_model':'x'}, {'bad':'value'}]}
 client=AIClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
 assert asyncio.run(client.models())==['qwen2.5:3b']


def test_remote_alias_rejected_before_sending_question():
 paths=[]
 def respond(request):
  paths.append(request.url.path)
  if request.url.path=='/api/show':
   return httpx.Response(200,json={'remote_model':'large-model','remote_host':'https://ollama.com'})
  return httpx.Response(200,json={'message':{'content':'bad'},'done':True})
 client=AIClient(model='alias',transport=httpx.MockTransport(respond))
 with pytest.raises(AIError): asyncio.run(client.reply('private question'))
 assert paths==['/api/show']
