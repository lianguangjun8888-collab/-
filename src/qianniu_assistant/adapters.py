"""接入边界：模拟会话永远不冒充千牛连接。"""


class SimulationAdapter:
    label = '模拟调试（不会向千牛发送）'
    live = False

    def __init__(self):
        self.sent = []

    async def send(self, event, text):
        self.sent.append((event.shop, event.conversation, event.event_id, text))
        return True


class UnavailableAdapter:
    label = '千牛接入未验证，真实发送不可用'
    live = False

    async def send(self, event, text):
        raise RuntimeError('尚未在 Windows 千牛 9.1907n 验证接入能力')
