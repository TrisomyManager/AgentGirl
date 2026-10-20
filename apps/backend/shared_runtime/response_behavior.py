"""A reusable response policy derived from continuous emotion and user context."""

from dataclasses import dataclass

from shared_contracts.models import EmotionState


@dataclass(frozen=True)
class ResponseBehavior:
    temperature: float
    max_tokens: int
    instruction: str
    emoji: str | None = None


def response_behavior(emotion: EmotionState | None, *, user_message="", intent="chat") -> ResponseBehavior:
    if intent in {"tool_use", "device_command", "task"} or any(
        word in user_message for word in ("代码", "步骤", "分析", "方案", "解释")
    ):
        return ResponseBehavior(0.35, 2048, "先完整回应用户的任务，按需要提供步骤和细节。表达清楚温和，不使用 emoji。")
    serious = intent in {"support", "tool_use", "device_command", "task"} or any(
        word in user_message for word in ("难过", "害怕", "焦虑", "失眠", "绝望", "生病", "去世")
    )
    if serious or (emotion and emotion.valence < -0.1):
        return ResponseBehavior(
            0.45, 768, "先简短温柔地回应情绪，不说教，不强行积极，不使用 emoji。用户需要步骤或详细分析时充分解释。"
        )
    if emotion and emotion.valence > 0.4 and emotion.arousal > 0.45:
        return ResponseBehavior(
            0.8, 1280, "语气轻快自然，可适度分享喜悦。可使用一个贴合语境的 emoji，不要每句都用。", "😊"
        )
    return ResponseBehavior(0.6, 1024, "语气平稳温暖，日常闲聊简洁。最多一个自然的 emoji，严肃话题不用。")
