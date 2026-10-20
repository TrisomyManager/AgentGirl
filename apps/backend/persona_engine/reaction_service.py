"""Compose independent classification, preview and commit without host imports."""

from datetime import UTC, datetime

from persona_engine.reaction import ReactionClassifier, rule_reaction
from persona_engine.relationship_tracker import apply_interaction


class ReactionService:
    def __init__(self, emotion_engine, relationship_tracker, classifier=None):
        self.engine = emotion_engine
        self.tracker = relationship_tracker
        self.classifier = classifier or ReactionClassifier()

    def predict(self, current, relationship, reaction, *, baseline=None, now=None):
        return self.engine.predict(
            current,
            relationship,
            sentiment=reaction.sentiment,
            valence=reaction.valence,
            arousal=reaction.arousal,
            confidence=reaction.confidence,
            baseline=baseline,
            now=now,
        ).model_copy(update={"trigger": f"reaction:{reaction.source}"})

    async def commit(self, user_id, turn_id, message, reaction=None, *, baseline=None):
        reaction = reaction or rule_reaction(message)
        now = datetime.now(UTC)

        def mutate(emotion, relationship):
            relationship = self.tracker._apply_decay(relationship)
            emotion = self.predict(emotion, relationship, reaction, baseline=baseline, now=now)
            relationship = apply_interaction(
                relationship,
                sentiment=reaction.sentiment,
                has_disclosure=reaction.has_disclosure,
                is_routine=reaction.is_routine,
                shared_experience=reaction.shared_experience,
                hostile=reaction.hostile,
                now=now,
            )
            return emotion, relationship

        store = self.engine.state_store or self.tracker.state_store
        if store:
            return await store.update(user_id, mutate, event_id=f"turn:{turn_id}")
        # Hosts may deliberately inject transient engines for an SDK prototype.
        emotion, relationship = mutate(
            await self.engine.get_current_emotion(user_id), await self.tracker.get_metrics(user_id)
        )
        await self.engine.set_emotion(user_id, emotion)
        await self.tracker._persist(relationship)
        return emotion, relationship
