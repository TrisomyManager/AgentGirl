"""User dashboard / state API.

GET /actions/user_state?user_id=user_001

Returns what Xiaonuan is currently doing for this user:
upcoming reminders, recent activity, proactive care rules, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from action_executor.reminders import get_reminders_store


async def build_user_state(user_id: str) -> dict[str, Any]:
    """Return a user-centred dashboard snapshot.

    This is intentionally read-only and cheap — it queries the existing
    reminders store and returns structured, user-facing data.
    """
    store = get_reminders_store()

    # All reminders for this user (include fired + cancelled so we can
    # show recent activity).
    all_reminders = await store.list_for_user(
        user_id=user_id,
        include_fired=True,
        include_cancelled=True,
    )

    upcoming: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for r in all_reminders:
        entry = {
            "id": r.id,
            "title": r.text,
            "scheduled_at": r.fire_at.isoformat(),
            "status": r.status,
            "source": "chat",
            "created_at": r.created_at.isoformat(),
        }
        if r.fired_at:
            entry["completed_at"] = r.fired_at.isoformat()
        if r.cancelled_at:
            entry["cancelled_at"] = r.cancelled_at.isoformat()

        if r.status == "pending":
            upcoming.append(entry)
        else:
            recent.append(entry)

    # Sort upcoming by fire_at asc, recent by fire_at desc
    upcoming.sort(key=lambda x: x["scheduled_at"])
    recent.sort(key=lambda x: x.get("completed_at") or x.get("cancelled_at") or x["scheduled_at"], reverse=True)

    # Keep only the 20 most recent to avoid blowing up the response
    recent = recent[:20]

    return {
        "user_id": user_id,
        "reminders": {
            "upcoming": upcoming,
            "recent": recent,
        },
        "tasks": {
            "open": [],
            "completed_recent": [],
        },
        "proactive": {
            "rules": [],
        },
    }
