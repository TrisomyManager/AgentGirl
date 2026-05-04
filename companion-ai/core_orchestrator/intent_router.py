"""LLM-based intent classification router for user messages."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from shared.config import get_settings

logger = structlog.get_logger()


class Intent(str, Enum):
    """Supported user intents."""

    CHAT = "chat"
    MEMORY_QUERY = "memory_query"
    TOOL_USE = "tool_use"
    ACTION_REQUEST = "action_request"
    DEVICE_COMMAND = "device_command"


INTENT_ROUTER_SYSTEM_PROMPT = """You are an intent classifier.
Classify the user's message into one of these intents and return strict JSON:
- chat
- memory_query
- tool_use
- action_request
- device_command

Response format:
{
  "intent": "<chat|memory_query|tool_use|action_request|device_command>",
  "confidence": 0.0-1.0,
  "reasoning": "short explanation",
  "entities": {"key": "value"}
}
"""

_MEMORY_KEYWORDS = (
    "记得",
    "还记得",
    "之前",
    "上次",
    "刚才",
    "以前",
    "我说过",
    "我喜欢什么",
    "我叫什么",
)
_TOOL_KEYWORDS = (
    "天气",
    "搜索",
    "查一下",
    "帮我查",
    "计算",
    "翻译",
    "几点",
    "汇率",
    "新闻",
)
_ACTION_KEYWORDS = (
    "抱抱",
    "挥手",
    "点头",
    "笑一个",
    "做个动作",
    "表情",
    "眨眼",
    "卖个萌",
)
_DEVICE_KEYWORDS = (
    "打开",
    "关闭",
    "开灯",
    "关灯",
    "空调",
    "音量",
    "设备",
    "播放音乐",
    "暂停",
)


class IntentResult:
    """Structured result of intent classification."""

    def __init__(
        self,
        intent: Intent,
        confidence: float,
        reasoning: str,
        entities: Dict[str, Any],
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.reasoning = reasoning
        self.entities = entities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "entities": self.entities,
        }


class IntentRouter:
    """Routes a user message to an intent using an LLM or local heuristics."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.settings = get_settings()
        self.model_name = model_name or self.settings.default_llm_model
        self._llm: Optional[ChatOpenAI] = None

    def _can_use_llm(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self.model_name,
                temperature=0.0,
                openai_api_key=self.settings.openai_api_key or "",
                openai_api_base=self.settings.openai_base_url or None,
            )
        return self._llm

    def _heuristic_classify(
        self,
        user_message: str,
        session_context: Optional[str] = None,
    ) -> IntentResult:
        text = user_message.lower().strip()
        combined_text = f"{text} {(session_context or '').lower()}".strip()

        if any(token in combined_text for token in _MEMORY_KEYWORDS):
            return IntentResult(Intent.MEMORY_QUERY, 0.72, "Matched memory keywords", {})

        if any(token in combined_text for token in _DEVICE_KEYWORDS):
            return IntentResult(
                Intent.DEVICE_COMMAND,
                0.7,
                "Matched device control keywords",
                {"command": user_message},
            )

        if any(token in combined_text for token in _ACTION_KEYWORDS):
            return IntentResult(Intent.ACTION_REQUEST, 0.68, "Matched avatar/action keywords", {})

        if any(token in combined_text for token in _TOOL_KEYWORDS):
            return IntentResult(Intent.TOOL_USE, 0.66, "Matched tool-use keywords", {})

        return IntentResult(Intent.CHAT, 0.6, "Defaulted to chat", {})

    async def classify(
        self,
        user_message: str,
        session_context: Optional[str] = None,
    ) -> IntentResult:
        """Classify user message into one of the Intent categories."""
        if not self._can_use_llm():
            result = self._heuristic_classify(user_message, session_context)
            logger.info(
                "intent_classified_heuristic",
                intent=result.intent.value,
                confidence=result.confidence,
                reasoning=result.reasoning,
            )
            return result

        llm = self._get_llm()
        context_block = f"\nSession context:\n{session_context}\n" if session_context else ""
        prompt = (
            f"User message: {user_message}{context_block}\n"
            "Return the JSON intent classification result."
        )
        messages = [
            SystemMessage(content=INTENT_ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        try:
            response = await llm.ainvoke(messages)
            raw_text = response.content
            if isinstance(raw_text, str):
                raw_text = raw_text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text.removeprefix("```json").removesuffix("```").strip()
                elif raw_text.startswith("```"):
                    raw_text = raw_text.removeprefix("```").removesuffix("```").strip()
                parsed = json.loads(raw_text)
            else:
                parsed = raw_text
        except Exception as exc:
            logger.warning("intent_router_llm_failed", error=str(exc))
            parsed = self._heuristic_classify(user_message, session_context).to_dict()

        intent_str = parsed.get("intent", "chat")
        try:
            intent = Intent(intent_str)
        except ValueError:
            logger.warning("intent_router_unknown_intent", intent=intent_str)
            intent = Intent.CHAT

        result = IntentResult(
            intent=intent,
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=str(parsed.get("reasoning", "")),
            entities=dict(parsed.get("entities", {})),
        )
        logger.info(
            "intent_classified",
            intent=result.intent.value,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )
        return result

    def classify_sync(
        self,
        user_message: str,
        session_context: Optional[str] = None,
    ) -> IntentResult:
        """Synchronous wrapper for classify (useful in sync LangGraph nodes)."""
        import asyncio

        return asyncio.run(self.classify(user_message, session_context))


_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router
