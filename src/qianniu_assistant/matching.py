"""受限的关键词语法，无 eval 或用户正则表达式。"""
from dataclasses import dataclass, field
from functools import lru_cache
import unicodedata
from .models import Rule


@dataclass
class MatchResult:
    matched: bool
    normalized: str
    groups: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    extra = set('×$~+=|*～<>')
    return ''.join(c for c in text if not unicodedata.category(c).startswith('P') and c not in extra)


@lru_cache(maxsize=1024)
def parse(expression: str, match_type: str = 'contains'):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
        raise ValueError('关键词不能为空，且不能超过 4096 字')
    if match_type not in ('contains', 'exact'):
        raise ValueError('未知匹配类型')
    if any(c in expression for c in '-()（）'):
        raise ValueError('关键词不能含减号或括号')
    if match_type == 'exact' and any(c in expression for c in '+|&'):
        raise ValueError('完全匹配只支持用 # 分隔候选句')
    branches = []
    for branch in expression.split('#'):
        conjunction = []
        for group in branch.split('+'):
            ordered = []
            for step in group.split('&'):
                words = [normalize(w.strip()) for w in step.split('|')]
                if any(not w for w in words):
                    raise ValueError('运算符两侧必须有有效关键词')
                ordered.append(tuple(words))
            conjunction.append(tuple(ordered))
        branches.append(tuple(conjunction))
    return tuple(branches)


def _ordered(sequence, message):
    # Earliest end dominates every later end for the same prefix. Selecting the
    # earliest *end* (not first textual alternative) preserves valid overlaps.
    end = 0
    hit = []
    for alternatives in sequence:
        candidates = []
        for word in alternatives:
            start = message.find(word, end)
            if start >= 0:
                candidates.append((start + len(word), word))
        if not candidates:
            return None
        end, word = min(candidates)
        hit.append(word)
    return hit


def evaluate(expression: str, message: str, match_type: str = 'contains') -> MatchResult:
    tree = parse(expression, match_type)
    text = normalize(message)
    if not text.strip():
        return MatchResult(False, text)
    if match_type == 'exact':
        for branch in tree:
            word = branch[0][0][0]
            if text == word:
                return MatchResult(True, text, [word])
        return MatchResult(False, text)
    for branch in tree:
        hits = []
        for sequence in branch:
            found = _ordered(sequence, text)
            if found is None:
                break
            hits.extend(found)
        else:
            return MatchResult(True, text, hits)
    return MatchResult(False, text)


def validate_rule(rule: Rule) -> None:
    for key in ('id', 'name', 'expression', 'shop', 'category'):
        value = getattr(rule, key)
        if not isinstance(value, str) or len(value) > 4096:
            raise ValueError(f'{key} 必须是长度不超过 4096 的文本')
    if not rule.id.strip() or not rule.name.strip():
        raise ValueError('规则名称和标识不能为空')
    if type(rule.priority) is not int or not 0 <= rule.priority <= 9999:
        raise ValueError('优先级必须为 0～9999 的整数')
    if type(rule.enabled) is not bool or type(rule.favorite) is not bool:
        raise ValueError('启用和收藏必须是布尔值')
    if not isinstance(rule.replies, list) or not 1 <= len(rule.replies) <= 100:
        raise ValueError('请填写 1～100 条回复')
    if any(not isinstance(r, str) or not r.strip() or len(r) > 4000 for r in rule.replies):
        raise ValueError('每条回复须为 1～4000 字的有效文本')
    parse(rule.expression, rule.match_type)
