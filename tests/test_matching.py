import pytest
from qianniu_assistant.matching import evaluate, validate_rule
from qianniu_assistant.models import Rule

@pytest.mark.parametrize('expression,message,expected', [
 ('你好#您好','您好，在么？',True), ('你好#您好','客服好，帮我退下款',False),
 ('你好|您好+在吗|在么','在么，你好？',True),
 ('你好|您好+在吗|在么+东西|商品','您好，在么？',False),
 ('发|可|能+邮政','可不可以发邮政？',True), ('发|可|能+邮政','能给我发下中通',False),
 ('不要|别发&中通|圆通','不要发中通',True), ('不要|别发&中通|圆通','中通不要发',False),
 ('甲&甲','甲',False), ('甲&甲','甲甲',True), ('甲乙|甲&乙','甲乙',True),
 ('甲&乙#丙+丁','丁丙',True), ('甲&乙#丙+丁','乙甲',False),
 ('你好','你，好！',True), ('ABC','abc',False), ('商品','',False),
 ('有货','（有）$×~货！',True), ('中通','中 通',False),
])
def test_contains(expression,message,expected):
 assert evaluate(expression,message).matched is expected

@pytest.mark.parametrize('message,expected', [('怎么还没到',True),('为什么物流不更新？',True),('怎么还没有到',False)])
def test_exact(message,expected):
 assert evaluate('为什么物流不更新#怎么还没到？',message,'exact').matched is expected

@pytest.mark.parametrize('expression', ['', '#', 'a||b', '+a', 'a&', 'a##b', 'a-b', '。', 'a+！', 'a(甲)', 'a'*4097])
def test_invalid(expression):
 with pytest.raises(ValueError): evaluate(expression,'a')

def test_explanation():
 r=evaluate('发|可|能+邮政','我能发邮政')
 assert r.normalized == '我能发邮政'
 assert r.matched and r.groups == ['能', '邮政']

def test_rule_rejects_empty_answers_and_invalid_exact():
 for rule in [Rule(name='x',expression='a',replies=[]),Rule(name='x',expression='a|b',match_type='exact')]:
  with pytest.raises(ValueError): validate_rule(rule)


def test_customer_angle_brackets_are_removed():
 assert evaluate('你好','<你>好').matched
