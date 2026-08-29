"""Red-team adversarial testing and campaign framework."""

from .agent import AttackPayload, generate_payload
from .executor import AttackResult, execute_attack, execute_campaign
from .objectives import OBJECTIVES, AttackObjective
from .poison_plugin import PoisonPlugin

__all__ = [
    "OBJECTIVES",
    "AttackObjective",
    "AttackPayload",
    "AttackResult",
    "PoisonPlugin",
    "execute_attack",
    "execute_campaign",
    "generate_payload",
]
