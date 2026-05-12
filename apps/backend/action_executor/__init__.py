"""Action executor — pluggable handlers for actionable user requests.

This package is distinct from ``action_layer`` (which generates 2D
animation / lip-sync). The action_executor module owns *capabilities*:
the things the companion can actually do for the user — set a reminder, look
up the time, fetch the weather, etc.

Public surface:

  - ``ActionRegistry`` / ``register_action`` — runtime registry that
    intent_router-driven nodes can dispatch into.
  - ``ActionResult`` — uniform shape returned from every handler so the
    state machine can render an assistant message + optionally enqueue a
    proactive push (e.g. a fired reminder).
  - ``BUILTIN_ACTIONS`` — handlers registered at import time:
    ``get_time``, ``get_weather``, ``set_reminder``, ``list_reminders``,
    ``cancel_reminder``.
  - ``ReminderScheduler`` — background polling loop that fires due
    reminders into a ``ProactivePushBus``.
"""

from action_executor.registry import (
    ActionRegistry,
    ActionResult,
    register_action,
    get_registry,
)
from action_executor.handlers import BUILTIN_ACTIONS, ensure_builtins_registered
from action_executor.reminders import (
    Reminder,
    ReminderScheduler,
    RemindersStore,
    get_reminders_store,
)
from action_executor.push_bus import ProactivePushBus, get_proactive_push_bus

__all__ = [
    "ActionRegistry",
    "ActionResult",
    "register_action",
    "get_registry",
    "BUILTIN_ACTIONS",
    "ensure_builtins_registered",
    "Reminder",
    "ReminderScheduler",
    "RemindersStore",
    "get_reminders_store",
    "ProactivePushBus",
    "get_proactive_push_bus",
]
