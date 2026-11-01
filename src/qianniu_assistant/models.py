from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Rule:
    name: str
    expression: str
    replies: list[str] = field(default_factory=lambda: ['好的，稍等。'])
    id: str = field(default_factory=lambda: uuid4().hex)
    match_type: str = 'contains'
    shop: str = ''
    category: str = '通用'
    priority: int = 88
    enabled: bool = True
    favorite: bool = False


@dataclass(frozen=True)
class MessageEvent:
    shop: str
    conversation: str
    event_id: str
    text: str
    kind: str = 'buyer_text'
