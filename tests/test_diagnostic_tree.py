from qianniu_assistant.diagnostic_tree import collect_tree, assess_windows


class Node:
 def __init__(self,name,children=()): self.name=name; self.children=list(children)


def test_tree_preserves_shape_without_reading_names():
 root=Node('private buyer text',[Node('private answer')])
 def describe(n,depth): return {'depth':depth,'control_type':'Window' if depth==0 else 'Edit','class_name':'Qt5152QWindowIcon'}
 result=collect_tree(root,lambda n:n.children,describe)
 assert [n['depth'] for n in result['controls']]==[0,1]
 assert 'private' not in str(result)
 assert result['errors']==[] and not result['truncated']


def test_provider_error_is_not_mistaken_for_empty_children():
 def fail(n): raise OSError('private message in exception')
 result=collect_tree(Node('root'),fail,lambda n,d:{'depth':d})
 assert len(result['controls'])==1
 assert result['errors'][0]=={'stage':'children','depth':0,'error_type':'OSError'}
 assert 'private message' not in str(result)


def test_tree_limits_stop_cycles_and_deep_trees():
 root=Node('root'); root.children=[root]
 result=collect_tree(root,lambda n:n.children,lambda n,d:{'depth':d},max_depth=3)
 assert len(result['controls'])==4 and result['truncated']
 assert result['depth_limit_reached']
 wide=Node('r',[Node(str(i)) for i in range(100)])
 result=collect_tree(wide,lambda n:n.children,lambda n,d:{'depth':d},max_nodes=5)
 assert len(result['controls'])==5 and result['truncated']


def test_root_only_report_gets_actionable_blocker_not_ready():
 windows=[{'visible':True,'minimized':False,'uia_raw':{'controls':[{'depth':0}], 'errors':[]},'native_children':{'controls':[],'errors':[]}}]
 findings=assess_windows(windows)
 assert findings['status']=='root_only'
 assert not findings['live_ready']
 assert '客服' in findings['next_action']


def test_native_child_discovery_is_not_live_connection():
 windows=[{'visible':True,'minimized':False,'uia_raw':{'controls':[{'depth':0}], 'errors':[]},'native_children':{'controls':[{'class_name':'Chrome_RenderWidgetHostHWND'}],'errors':[]}}]
 result=assess_windows(windows)
 assert result['status']=='native_children_found'
 assert result['live_ready'] is False


def test_raw_descendants_still_require_identity_validation():
 windows=[{'visible':True,'minimized':False,'uia_raw':{'controls':[{'depth':0},{'depth':1}], 'errors':[]},'native_children':{'controls':[],'errors':[]}}]
 result=assess_windows(windows)
 assert result['status']=='uia_descendants_found'
 assert not result['live_ready']


def test_hidden_or_minimized_window_report_explains_state():
 r=assess_windows([{'visible':True,'minimized':True,'uia_raw':{'controls':[{'depth':0}]},'native_children':{'controls':[]}}])
 assert r['status']=='no_visible_chat_window'


def test_target_process_filter_never_inspects_our_own_packaged_app():
 from qianniu_assistant.windows_diagnostics import matches_target
 assert matches_target('AliWorkbench.exe')
 assert matches_target('qianniu.exe')
 assert not matches_target('QianniuLocalAssistant.exe')
 assert not matches_target('AliWorkbenchHelper.exe')
 assert not matches_target('notepad.exe')
