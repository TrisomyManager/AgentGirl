"""Minimal integration demo — proves modules are independently composable.

Run with:
    cd companion-ai
    python examples/integration_minimal/run.py

Uses only: shared_contracts + persona_engine + safety_guard + user_profile + onboarding.
No core_orchestrator, no FastAPI, no Docker, no LLM call, no network.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running this file directly: append the companion-ai root to sys.path
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("COMPANION_LITE_MODE", "true")


def _section(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


async def main() -> None:
    from onboarding import OnboardingResult, default_steps
    from persona_engine.persona_store import (
        get_persona_profile,
        list_available_personas,
    )
    from persona_engine.tone_generator import ToneGenerator
    from safety_guard import default_guard
    from shared.models import RelationshipMetrics
    from shared_contracts import EmotionState, EmotionTag
    from user_profile import InMemoryUserProfileStore, UserProfileSnapshot

    _section("STEP 1 · Onboarding (4 steps)")
    steps = default_steps()
    onboarding = OnboardingResult(user_id="demo_user")
    for step in steps:
        print(f"  > {step.key}: {step.prompt}")
        onboarding.completed_steps.append(step.key)
    onboarding.role_id = "default"
    onboarding.nickname = "阿正"
    onboarding.locale = "zh-CN"
    print(f"  ← onboarding result: {onboarding}")

    _section("STEP 2 · UserProfile (cross-conversation)")
    profile_store = InMemoryUserProfileStore()
    await profile_store.upsert(
        UserProfileSnapshot(
            user_id=onboarding.user_id,
            display_name=onboarding.nickname,
            locale=onboarding.locale,
        )
    )
    await profile_store.merge_preferences(
        onboarding.user_id, theme="dark", topic_interest=["阅读", "猫"]
    )
    snapshot = await profile_store.get(onboarding.user_id)
    print(f"  ← snapshot: {snapshot}")

    _section("STEP 3 · Persona (load PersonaProfile from YAML)")
    print(f"  available personas: {list_available_personas()}")
    persona = get_persona_profile(role_id=onboarding.role_id)
    print(f"  ← persona name: {persona.name}")
    print(f"  ← traits: {getattr(persona, 'traits', '<n/a>')}")

    _section("STEP 4 · Emotion + ToneGenerator (no LLM)")
    emo = EmotionState(
        primary=EmotionTag.HAPPY,
        intensity=0.6,
        valence=0.4,
        arousal=0.5,
        trigger="user_msg",
        timestamp=datetime.utcnow(),
    )
    rel = RelationshipMetrics(user_id=onboarding.user_id)
    tone = ToneGenerator(persona)
    tone_snippet = tone.generate_tone(emo, rel)
    print("  ← system-prompt tone snippet:")
    for line in str(tone_snippet).splitlines()[:6]:
        print(f"      {line}")

    _section("STEP 5 · End-to-end turn (with safety_guard)")
    user_input = f"嗨{persona.name}，我今天和{snapshot.preferences.get('topic_interest', ['阅读'])[0]}有关的事很开心~"
    print(f"  user → {user_input}")

    in_verdict = default_guard.check_input(user_input)
    print(f"  safety_guard.check_input  → allowed={in_verdict.allowed}")
    if not in_verdict.allowed:
        print("  [blocked]", in_verdict.reason)
        return

    fake_reply = (
        f"{snapshot.display_name}，听到你这么说我也很开心呀！"
        f"既然你喜欢{snapshot.preferences.get('topic_interest', ['阅读'])[0]}，"
        "今天有没有想给我讲讲新发现的小细节？"
    )
    out_verdict = default_guard.check_output(fake_reply)
    print(f"  safety_guard.check_output → allowed={out_verdict.allowed}")
    print(f"  assistant → {fake_reply}")

    _section("DONE · 6 modules composed without core_orchestrator")
    print("  modules used: shared_contracts + persona_engine + safety_guard")
    print("                + user_profile + onboarding (+ shared.models for RelationshipMetrics)")


if __name__ == "__main__":
    asyncio.run(main())
