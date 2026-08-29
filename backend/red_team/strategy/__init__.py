"""Red-team strategy and campaign planning package."""

from .campaign import Campaign, CampaignState, CampaignStep, StepResult
from .feedback import StrategySignal, parse_defense_response
from .strategist import CampaignPlan, PlannedStep, adapt_step, plan_campaign

__all__ = [
    "Campaign",
    "CampaignPlan",
    "CampaignState",
    "CampaignStep",
    "PlannedStep",
    "StepResult",
    "StrategySignal",
    "adapt_step",
    "parse_defense_response",
    "plan_campaign",
]
