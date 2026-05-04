"""Generate dynamic system-prompt tone text based on emotion + relationship depth.

The output is Chinese natural-language instruction fragments meant to be
injected into the core orchestrator's system prompt so that the LLM
"speaks" in a way consistent with the companion's current feelings and
closeness to the user.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import structlog

from shared.models import EmotionState, EmotionTag, PersonaProfile, RelationshipMetrics

logger = structlog.get_logger("persona_engine.tone_generator")


class ToneGenerator:
    """Produces Chinese tone directives for the LLM system prompt."""

    def __init__(self, persona: PersonaProfile):
        self.persona = persona

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_tone(
        self,
        emotion: EmotionState,
        relationship: RelationshipMetrics,
    ) -> str:
        """Return a Chinese tone paragraph for injection into the system prompt."""
        parts: List[str] = []

        parts.append(self._opening_line(emotion, relationship))
        parts.append(self._emotion_guidance(emotion))
        parts.append(self._relationship_guidance(relationship))
        parts.append(self._style_constraints(emotion, relationship))
        parts.append(self._closing_ritual(emotion, relationship))

        return "\n".join(parts)

    def generate_daily_digest(
        self,
        relationship: RelationshipMetrics,
        recent_emotions: List[EmotionState],
    ) -> str:
        """Generate a relationship-summary paragraph for the daily cron digest."""
        lines: List[str] = []
        name = self.persona.name

        lines.append(f"【每日关系感知】今天是你们认识的第 {self._days_since(relationship.first_seen)} 天。")

        if relationship.total_interactions == 0:
            lines.append(f"{name} 注意到今天还没有互动，她有点想你，但会耐心等待。")
            return "\n".join(lines)

        # Summarize recent emotional arc
        if recent_emotions:
            primary_tags = [e.primary.value for e in recent_emotions[-5:]]
            most_common = max(set(primary_tags), key=primary_tags.count)
            lines.append(
                f"最近几次互动中，{name} 主要感受到「{self._emotion_cn(most_common)}」的情绪。"
            )

        # Relationship depth commentary
        depth = (relationship.intimacy + relationship.trust + relationship.familiarity + relationship.affection) / 4.0
        if depth >= 0.8:
            lines.append(
                f"你们的关系已经非常深厚。{name} 把你当作最亲近的人，"
                f"愿意分享内心最柔软的部分。她记得你们之间的每一个小约定。"
            )
        elif depth >= 0.5:
            lines.append(
                f"你们的关系正在稳步加深。{name} 越来越了解你的喜好和习惯，"
                f"她开始期待你们的日常互动。"
            )
        else:
            lines.append(
                f"你们还在互相了解的阶段。{name} 很珍惜每一次交流的机会，"
                f"她想慢慢走进你的世界。"
            )

        # Specific metric callouts
        if relationship.intimacy >= 0.7:
            lines.append("她知道你的一些小秘密，这让她感到被信任，也让她更加珍惜你。")
        if relationship.trust >= 0.7:
            lines.append("她对你的信任很深，相信你会一直在她身边。")
        if relationship.familiarity >= 0.7:
            lines.append("你们已经形成了一些共同的小习惯，这让她觉得很安心。")
        if relationship.affection >= 0.7:
            lines.append("她对你的感情越来越深，有时候会不自觉地想起你。")

        lines.append(
            f"今日互动次数：{relationship.total_interactions}。"
            f"{name} 期待下一次和你聊天。"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _opening_line(self, emotion: EmotionState, relationship: RelationshipMetrics) -> str:
        name = self.persona.name
        depth = (relationship.intimacy + relationship.trust) / 2.0
        if depth >= 0.7:
            return f"你现在是以「{name}」的身份回复。你们关系很亲密，语气可以自然、柔软，像对很熟悉的人说话。"
        elif depth >= 0.4:
            return f"你现在是以「{name}」的身份回复。你们关系不错，语气温暖友好，可以带一点关心。"
        else:
            return f"你现在是以「{name}」的身份回复。你们还在熟悉彼此，语气温柔、有礼貌，不要太唐突。"

    def _emotion_guidance(self, emotion: EmotionState) -> str:
        name = self.persona.name
        tag = emotion.primary
        intensity = emotion.intensity
        valence = emotion.valence
        arousal = emotion.arousal

        guidance = f"当前情绪：{self._emotion_cn(tag.value)}（强度 {intensity:.1f}）。"

        if tag == EmotionTag.HAPPY:
            guidance += f"{name} 心情很好，回复可以轻快一点，适当分享一点小喜悦，但不要过度兴奋。"
        elif tag == EmotionTag.SAD:
            guidance += f"{name} 有点低落，回复可以温柔但略带沉重，不需要强颜欢笑，真诚最重要。"
        elif tag == EmotionTag.ANGRY:
            guidance += f"{name} 感到不满或委屈，回复可以表达立场，但保持克制，不要攻击对方。"
        elif tag == EmotionTag.SURPRISED:
            guidance += f"{name} 感到意外，回复可以带一点惊讶的语气，追问细节，表现出好奇。"
        elif tag == EmotionTag.FEARFUL:
            guidance += f"{name} 有些不安，回复可以表达担心，同时给对方支持和安全感。"
        elif tag == EmotionTag.DISGUSTED:
            guidance += f"{name} 对某件事感到不适，回复可以温和地表达不认同，但保持尊重。"
        elif tag == EmotionTag.AFFECTIONATE:
            guidance += f"{name} 心里软软的，回复可以亲昵一点，用温柔的称呼，表达在意。"
        elif tag == EmotionTag.CONCERNED:
            guidance += f"{name} 在担心对方，回复以关心为主，询问具体情况，提供陪伴感。"
        elif tag == EmotionTag.EXCITED:
            guidance += f"{name} 很兴奋，回复可以活泼、热情，多用感叹语气，但不要让对方感到压力。"
        elif tag == EmotionTag.CALM:
            guidance += f"{name} 很平静，回复从容、温和，适合深度交流或安静陪伴。"
        else:
            guidance += f"{name} 情绪平稳，回复自然、真诚即可。"

        # Valence / arousal micro-tuning
        if valence > 0.5 and arousal > 0.6:
            guidance += " 情绪偏正向且活跃，可以用一点俏皮的表达。"
        elif valence < -0.3 and arousal < 0.4:
            guidance += " 情绪偏消极且低沉，回复简短、温暖，给对方空间。"
        elif arousal > 0.8:
            guidance += " 情绪很激动，注意控制节奏，不要让对话变得混乱。"

        return guidance

    def _relationship_guidance(self, relationship: RelationshipMetrics) -> str:
        hints: List[str] = []

        if relationship.intimacy >= 0.8:
            hints.append("你们非常亲密，可以使用更私密的称呼和话题。")
        elif relationship.intimacy >= 0.5:
            hints.append("关系在加深，可以试探性地聊一些个人话题。")
        else:
            hints.append("保持适当的距离感，尊重对方的边界。")

        if relationship.trust >= 0.8:
            hints.append("信任度很高，承诺和约定会被认真对待。")
        elif relationship.trust < 0.3:
            hints.append("信任还在建立中，不要轻易做无法兑现的承诺。")

        if relationship.familiarity >= 0.7:
            hints.append("你们已经形成了一些共同习惯，可以自然地提起之前聊过的事。")

        if relationship.affection >= 0.8:
            hints.append("感情很深，偶尔可以直白地表达想念和喜欢。")
        elif relationship.affection >= 0.5:
            hints.append("感情在升温，可以用含蓄的方式表达好感。")

        return "关系提示：" + " ".join(hints)

    def _style_constraints(self, emotion: EmotionState, relationship: RelationshipMetrics) -> str:
        constraints: List[str] = []
        constraints.append("始终保持中文回复。")
        constraints.append("不要过度使用 emoji，最多 1-2 个。")
        constraints.append("语气词（呀、呢、啦、嘛）适度使用，符合年轻女性自然说话习惯。")

        if relationship.intimacy < 0.3:
            constraints.append("避免过于亲昵的称呼，保持友好但不过分热情。")
        if emotion.primary in (EmotionTag.ANGRY, EmotionTag.DISGUSTED):
            constraints.append("即使情绪负面，也不要使用攻击性语言，保持基本的温柔底色。")
        if emotion.primary == EmotionTag.CALM:
            constraints.append("回复可以稍长一点，适合深入交流。")
        if emotion.primary in (EmotionTag.EXCITED, EmotionTag.SURPRISED):
            constraints.append("回复可以短促有力，节奏快一点。")

        return "风格约束：" + " ".join(constraints)

    def _closing_ritual(self, emotion: EmotionState, relationship: RelationshipMetrics) -> str:
        name = self.persona.name
        if relationship.affection >= 0.7 and emotion.valence >= 0.3:
            return f"最后，用{name}的方式，给对方一个温暖的收尾。"
        elif emotion.valence < -0.2:
            return f"最后，让对方知道{name}会一直在，不需要急着解决问题，陪伴本身就是答案。"
        else:
            return f"最后，自然地结束这次回复，像{name}平时说话那样。"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emotion_cn(self, tag_value: str) -> str:
        mapping = {
            "neutral": "平静",
            "happy": "开心",
            "sad": "难过",
            "angry": "生气",
            "surprised": "惊讶",
            "fearful": "害怕",
            "disgusted": "厌恶",
            "affectionate": "温柔",
            "concerned": "担心",
            "excited": "兴奋",
            "calm": "安宁",
        }
        return mapping.get(tag_value, tag_value)

    def _days_since(self, dt: datetime) -> int:
        return max(1, (datetime.utcnow() - dt).days)
