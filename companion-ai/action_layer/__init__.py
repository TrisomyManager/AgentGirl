"""Action Layer — 2D photo-driven action generation, lip sync, and sequencing for companion-ai."""

from .generator_2d import Action2DGenerator
from .lip_sync import LipSyncGenerator
from .router import ActionRouter
from .sequencer import ActionSequencer

__all__ = [
    "Action2DGenerator",
    "ActionRouter",
    "LipSyncGenerator",
    "ActionSequencer",
]
