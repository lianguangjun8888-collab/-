import pytest
from qianniu_assistant.windows_diagnostics import prioritize_windows, select_renderers, describe_element
from qianniu_assistant.diagnostic_tree import collect_tree, assess_windows


def test_visible_chat_is_not_excluded_by_many_hidden_windows():
 handles=list(range(30))+[100,101]
 ordered=prioritize_windows(handles,lambda h:h>=100,lambda h:h==101)
 assert ordered[:2]==[100,101]
 assert 100 in ordered[:20]


def test_renderer_selection_prefers_large_visible_chat_and_deduplicates():
 records=[{'handle':1,'class_name':'Chrome_RenderWidgetHostHWND','visible':False,'rect':[0,0,4000,3000]},
          {'handle':2,'class_name':'Chrome_RenderWidgetHostHWND','visible':True,'rect':[0,0,200,400]},
          {'handle':3,'class_name':'Chrome_RenderWidgetHostHWND','visible':True,'rect':[0,0,1200,800]},
          {'handle':3,'class_name':'Chrome_RenderWidgetHostHWND','visible':True,'rect':[0,0,1200,800]},
          {'handle':4,'class_name':'Other','visible':True,'rect':[0,0,6000,5000]}]
 assert [n['handle'] for n in select_renderers(records)]==[3,2]


class UI:
 known_control_type_ids={50004:'Edit'}
 class UIA_dll: pass


class Element:
 CurrentControlType=50004
 CurrentClassName=''
 CurrentAutomationId='editor'
 CurrentFrameworkId='Chrome'
 CurrentIsOffscreen=False
 CurrentNativeWindowHandle=100
 CurrentProcessId=123
 CurrentBoundingRectangle=type('Rect',(),dict(left=1,top=2,right=30,bottom=40))()
 def GetRuntimeId(self): return [42,10,7]
 @property
 def CurrentName(self): raise AssertionError('default probe must not read names')


def test_uia_metadata_does_not_read_name_or_text_value():
 node=describe_element(Element(),UI(),3,False)
 assert node['automation_id']=='editor'
 assert node['runtime_id']==[42,10,7]
 assert node['native_handle']==100
 assert node['rect']==[1,2,30,40]
 assert 'name' not in node


def test_deep_tree_paths_locate_editor_beyond_old_depth_limit():
 root={'type':'Document','children':[]}; current=root
 for i in range(15):
  child={'type':'Group','children':[]}; current['children'].append(child); current=child
 current['children'].append({'type':'Edit','children':[]})
 result=collect_tree(root,lambda n:n['children'],lambda n,d:{'depth':d,'control_type':n['type']},max_depth=32,with_paths=True)
 editor=[n for n in result['controls'] if n['control_type']=='Edit'][0]
 assert editor['depth']==16 and editor['path']==[0]*16
 assert not result['truncated']


def test_targeted_edit_candidates_do_not_claim_live_ready():
 windows=[{'visible':True,'minimized':False,'uia_raw':{'controls':[{'depth':0}]},
           'native_children':{'controls':[]},'renderers':[{'uia_raw':{'status':'completed','controls':[],
           'input_candidates':[{'control_type':'Edit','automation_id':'editor'}]}}]}]
 result=assess_windows(windows)
 assert result['status']=='input_candidates_found'
 assert not result['live_ready']


@pytest.mark.parametrize('renderer_count',[1,5])
def test_real_collector_prioritizes_chat_and_probes_renderers(monkeypatch,renderer_count):
 import sys
 from copy import deepcopy
 from types import SimpleNamespace as NS
 import qianniu_assistant.windows_diagnostics as native
 class Handle:
  def Close(self): pass
 def version(*args): raise OSError('no version fixture')
 api=NS(OpenProcess=lambda *a:Handle(),GetFileVersionInfo=version)
 process=NS(GetWindowThreadProcessId=lambda h:(1,50),GetModuleFileNameEx=lambda *a:'AliWorkbench.exe')
 def enum_windows(callback,arg):
  for h in list(range(1,26))+[100]: callback(h,arg)
 def enum_children(hwnd,callback,arg):
  if hwnd==100:
   for child in range(200,200+renderer_count): callback(child,arg)
 gui=NS(EnumWindows=enum_windows,EnumChildWindows=enum_children,IsWindowVisible=lambda h:h==100 or 200<=h<200+renderer_count,
        IsIconic=lambda h:False,GetParent=lambda h:100,GetClassName=lambda h:'Chrome_RenderWidgetHostHWND',
        IsWindowEnabled=lambda h:True,GetWindowRect=lambda h:(0,0,1200,800),SendMessageTimeout=lambda *a:(1,0))
 security=NS(OpenProcessToken=lambda *a:Handle(),GetTokenInformation=lambda *a:0,TokenElevation=20)
 for name,value in [('win32api',api),('win32gui',gui),('win32process',process),('win32security',security)]:
  monkeypatch.setitem(sys.modules,name,value)
 monkeypatch.setattr(native.ctypes,'windll',NS(shell32=NS(IsUserAnAdmin=lambda:False)),raising=False)
 def raw(hwnd,include_names,**kwargs):
  if hwnd>=200:
   root={'type':'Document','children':[]}; current=root
   for i in range(15):
    child={'type':'Group','children':[]}; current['children'].append(child); current=child
   current['children'].append({'type':'Edit','children':[]})
   return collect_tree(root,lambda n:n['children'],lambda n,d:{'depth':d,'control_type':n['type']},
                       max_depth=kwargs.get('max_depth',6))
  return {'controls':[{'depth':0,'control_type':'Window'}],'errors':[]}
 monkeypatch.setattr(native,'_raw_tree',raw)
 checkpoints=[]
 result=native.collect_windows(on_window=lambda entry:checkpoints.append(deepcopy(entry)))
 chat=result['windows'][0]
 assert chat['handle']==100
 assert len(chat['renderers'])==min(renderer_count,4)
 assert chat.get('renderers_truncated',False) is (renderer_count>4)
 renderer=chat['renderers'][0]
 assert any(n['control_type']=='Edit' for n in renderer['uia_raw']['controls'])
 assert checkpoints and checkpoints[0]['handle']==100


def test_password_flag_from_com_boolean_never_reads_name():
 class Protected(Element): CurrentIsPassword=1
 node=describe_element(Protected(),UI(),0,True)
 assert node['is_password'] is True and 'name' not in node


def test_raw_candidate_query_preserves_early_progress_and_privacy(monkeypatch):
 import sys
 from types import ModuleType,SimpleNamespace as NS
 from copy import deepcopy
 from qianniu_assistant.windows_diagnostics import _raw_tree
 class Item(Element):
  CurrentIsPassword=False
  def __init__(self,id,kind,children=(),offscreen=False,password=False):
   self.CurrentAutomationId=id; self.CurrentControlType=kind
   self.children=list(children); self.CurrentIsOffscreen=offscreen; self.CurrentIsPassword=password
  def FindAll(self,scope,kind):
   found=[n for n in self.children if n.CurrentControlType==kind]
   return NS(Length=len(found),GetElement=lambda i:found[i])
 normal=Item('editor',50004)
 password=Item('password',50004,password=True)
 hidden=Item('hidden',50004,offscreen=True)
 unknown=Item('unknown',50004,password=None)
 send=Item('button',50000)
 root=Item('document',50030,[normal,password,hidden,unknown,send])
 parent={id(n):root for n in root.children}
 def sibling(n):
  nodes=parent[id(n)].children; index=nodes.index(n)
  return nodes[index+1] if index+1<len(nodes) else None
 walker=NS(GetFirstChildElement=lambda n:n.children[0] if n.children else None,GetNextSiblingElement=sibling)
 ui=NS(known_control_type_ids={50004:'Edit',50000:'Button',50030:'Document'},known_control_types={'Edit':50004,'Button':50000},
       tree_scope={'descendants':4},UIA_dll=NS(UIA_ControlTypePropertyId=30003),
       iuia=NS(RawViewWalker=walker,ElementFromHandle=lambda h:root,CreatePropertyCondition=lambda p,k:k))
 pkg=ModuleType('pywinauto'); pkg.__path__=[]
 definitions=ModuleType('pywinauto.uia_defines'); definitions.IUIA=lambda:ui
 monkeypatch.setitem(sys.modules,'pywinauto',pkg); monkeypatch.setitem(sys.modules,'pywinauto.uia_defines',definitions)
 saved=[]
 result=_raw_tree(100,False,targeted=True,on_progress=lambda data:saved.append(deepcopy(data)))
 assert [n['automation_id'] for n in result['input_candidates']]==['editor']
 assert [n['automation_id'] for n in result['button_candidates']]==['button']
 assert saved[0]['controls']==[] and saved[0]['input_candidates']
 assert all('name' not in n for n in result['controls'])


def test_unknown_password_state_does_not_read_name():
 class Unknown(Element):
  @property
  def CurrentIsPassword(self): raise OSError('provider unavailable')
  CurrentName='private label'
 node=describe_element(Unknown(),UI(),0,True)
 assert node['is_password'] is None
 assert 'name' not in node
