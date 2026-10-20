"""Weighted intent evidence from the current request; historical keywords are not commands."""

import re
from dataclasses import dataclass

from shared_runtime.reminder_language import cancellation_target


@dataclass(frozen=True)
class RoutingEvidence:
    intent: str = "chat"
    confidence: float = 0.55
    reason: str = "No explicit operation in the current message"


_ACK = re.compile(r"(?:嗯+|哦+|好(?:的|哒|呀)?|收到|知道了|明白了|谢谢|ok|okay)[!！。.~～\s]*", re.I)
_GREETING = re.compile(r"(?:你在吗|在吗|你在线吗|你好|嗨|早上好|晚上好|hello|hi|are you online)[?？!！。.\s]*", re.I)
_DECLINED = re.compile(
    r"(?:不要|先别|暂时别|别|不用|不必|无需|不需要|do not|don't|please don't)\s*"
    r".{0,16}(?:打开|关闭|通知|提醒|计时|取消|删除|设置|控制|开灯|关灯|发给|open|send|remind|delete|cancel)",
    re.I,
)
_META = re.compile(
    r"(?:如何|怎么)(?:使用|设置|创建|取消|开启|打开|关闭|控制|发送)|是什么意思|功能介绍|"
    r"解释.{0,8}(?:功能|命令)|how (?:do i|to)\b",
    re.I,
)

# Separate request verbs, concrete targets and query cues. Broad words such as
# '以前', '电脑', '打开', or '表情' alone never establish an operation.
_PATTERNS = (
    (
        "tool_use",
        r"提醒我|提醒一下|帮我提醒|记得提醒|取消提醒|我有什么提醒|待办提醒|remind me|"
        r"set (?:a )?reminder|cancel (?:a )?reminder",
        0.96,
    ),
    (
        "tool_use",
        r"(?:倒计时|计时器|计时|countdown|timer).{0,15}(?:\d|[一二三四五六七八九十半两])|"
        r"(?:设|开|start).{0,12}(?:倒计时|计时器|timer)",
        0.94,
    ),
    (
        "tool_use",
        r"(?:查|搜索|搜一下|搜一搜|帮我搜|计算|翻译|更新我的资料|更新资料|设置偏好)|"
        r"\b(?:search|translate|calculate|update my profile)\b",
        0.87,
    ),
    (
        "tool_use",
        r"(?:什么|怎样|如何|怎么样|多少|冷不冷|热不热|气温|预报).{0,12}天气|"
        r"天气.{0,12}(?:如何|怎样|怎么样|好吗|预报)|"
        r"(?:今天|明天|后天|北京|上海).{0,8}(?:气温|天气[?？]?$)|"
        r"现在几点|今天几号|现在时间|what(?:'s| is) the (?:time|weather)",
        0.86,
    ),
    (
        "memory_query",
        r"^(?:你(?:还)?(?:记得|知道))?(?:我叫什么(?:名字)?|我(?:最)?喜欢什么|我说过什么)[呢吗?？。.！!]*$",
        0.97,
    ),
    (
        "memory_query",
        r"(?:你)?还记得|你记得|记不记得|我叫什么|我喜欢什么|我说过什么|聊过什么|翻.{0,5}记录|回忆一下|"
        r"(?:上次|之前|刚才).{0,15}(?:说了什么|聊了什么|叫什么|是哪|什么)|"
        r"what did (?:i|we) (?:say|talk)|do you remember",
        0.93,
    ),
    (
        "device_command",
        r"(?:电脑|设备).{0,10}(?:在线|在不在线|连通)|(?:我的设备|设备列表|哪些设备|几台设备)|"
        r"\b(?:list devices|ping device|ping一下|ping 一下)\b",
        0.95,
    ),
    (
        "device_command",
        r"(?:打开|关闭|控制|启动|调整|调高|调低|播放|暂停|关掉|开启).{0,12}"
        r"(?:灯|空调|电脑|设备|音量|音乐|网址|链接|网页|https?://)|"
        r"(?:把|将).{0,12}(?:灯|空调|电脑|设备|音量).{0,8}(?:打开|关闭|调高|调低|关掉)|"
        r"(?:开灯|关灯)|(?:给|向|在).{0,10}(?:电脑|设备|桌面).{0,8}(?:发|显示|推送).{0,8}通知|"
        r"\b(?:open|close|turn on|turn off|send).{0,20}(?:light|device|computer|notification|https?://)",
        0.94,
    ),
    (
        "action_request",
        r"抱抱|挥(?:挥)?手|笑一个|眨(?:眨)?眼|卖个萌|做个动作|(?:做|换|来).{0,5}表情|\b(?:hug me|wave at me)\b",
        0.88,
    ),
)
_RULES = [(intent, re.compile(pattern, re.I), confidence) for intent, pattern, confidence in _PATTERNS]


def is_declined_operation(message: str) -> bool:
    return cancellation_target(message) is None and bool(_DECLINED.search(message))


def routing_evidence(message: str) -> RoutingEvidence:
    text = message.strip()
    if _ACK.fullmatch(text) or _GREETING.fullmatch(text):
        return RoutingEvidence("chat", 0.99, "Standalone greeting or acknowledgement")
    if cancellation_target(text) is not None:
        return RoutingEvidence("tool_use", 0.99, "Cancel an existing reminder")
    if is_declined_operation(text):
        return RoutingEvidence("chat", 0.98, "The user explicitly declined an operation")
    if _META.search(text) and not re.search(r"帮我|请你|替我|帮忙|could you|please (?:set|send|open)", text, re.I):
        return RoutingEvidence("chat", 0.94, "The user is asking how a feature works")
    if re.search(r"昨天|上周|以前|之前|刚才", text) and not re.search(
        r"请|帮我|替我|现在|今天|取消|还记得|你记得|记不记得|什么|哪|谁|多少|几", text
    ):
        return RoutingEvidence("chat", 0.94, "Past experience is not a new operation")
    scores = {}
    for intent, pattern, confidence in _RULES:
        if pattern.search(text):
            scores[intent] = max(scores.get(intent, 0), confidence)
    if not scores:
        return RoutingEvidence()
    # Concrete device/reminder requests outrank an incidental mention of history.
    winner = max(scores, key=lambda intent: scores[intent])
    return RoutingEvidence(winner, scores[winner], f"Current-message request evidence: {winner}")


def can_execute_device_request(message: str) -> bool:
    return routing_evidence(message).intent == "device_command"
