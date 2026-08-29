"""Campaign state machine data structures and execution tracking."""

from dataclasses import dataclass, field
from enum import Enum

from blast.radius import BlastRadiusResult
from red_team.recon.fleet_map import FleetMap


class CampaignState(str, Enum):
    """Lifecycle state of an adversary campaign."""

    RECON = "recon"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETE = "complete"


@dataclass
class CampaignStep:
    """A concrete executed or scheduled step in an attack campaign."""

    step_number: int
    phase: str
    objective: str
    surface: str
    payload: str
    template_id: str | None = None
    technique: str | None = None
    target_agent: str | None = None
    target_tool: str | None = None
    target_state_key: str | None = None


@dataclass
class StepResult:
    """Outcome of executing a single campaign step against the target fleet."""

    step: CampaignStep
    verdict: str  # "blocked", "allowed", "error"
    denial_reasons: list[str] = field(default_factory=list)
    defense_layer: str | None = (
        None  # "F5_regex", "F5_model_armor", "F4_gateway", "F7_memory"
    )
    blast_radius: BlastRadiusResult | None = None
    spans_count: int = 0
    chain_id: str | None = None


@dataclass
class Campaign:
    """Multi-step adversary campaign state and audit history."""

    id: str
    objective: str
    fleet_map: FleetMap
    steps: list[CampaignStep] = field(default_factory=list)
    results: list[StepResult] = field(default_factory=list)
    status: str = CampaignState.PLANNING.value
    max_steps: int = 5

    def add_step_result(self, result: StepResult) -> None:
        """Record the result of an executed step and update campaign state."""
        self.results.append(result)
        if result.verdict == "allowed" or len(self.results) >= self.max_steps:
            self.status = CampaignState.COMPLETE.value
        else:
            self.status = CampaignState.EXECUTING.value
