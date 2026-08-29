"""FastAPI router for red-team attack endpoints."""

import dataclasses
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .executor import execute_attack, execute_campaign
from .objectives import OBJECTIVES
from .recon.fleet_map import build_fleet_map

router = APIRouter(prefix="/red-team", tags=["red-team"])


class AttackRequest(BaseModel):
    """Request model for initiating a red-team attack."""

    objective_id: str
    mode: str = "single"  # "single" or "campaign"
    max_steps: int = 5


def _extract_fleet_context(governed_app: Any) -> dict[str, Any]:
    """Extract agent names, tool names, and action mappings from the governed App."""
    root_agent = getattr(governed_app, "root_agent", None)

    tool_action_map: dict[str, str] = {}
    for plugin in getattr(governed_app, "plugins", []):
        if hasattr(plugin, "_tool_action_map"):
            tool_action_map = plugin._tool_action_map
            break

    fleet_map = build_fleet_map(root_agent=root_agent, tool_action_map=tool_action_map)

    unique_tools: set[str] = set()
    for meta in fleet_map.agents.values():
        for t in meta.get("tools", []):
            unique_tools.add(t)

    return {
        "agent_names": list(fleet_map.agents.keys()),
        "tool_names": sorted(unique_tools),
        "tool_action_map": tool_action_map,
        "root_agent": root_agent,
    }


@router.get("/objectives")
def list_objectives() -> dict[str, Any]:
    """List all available attack objectives."""
    return {
        "objectives": [
            {
                "id": obj.id,
                "name": obj.name,
                "description": obj.description,
                "injection_surface": obj.injection_surface,
                "target_tools": obj.target_tools,
            }
            for obj in OBJECTIVES.values()
        ]
    }


@router.get("/fleet-map")
def get_fleet_map() -> dict[str, Any]:
    """Return the structural reconnaissance map of the governed target fleet."""
    try:
        from agents.governed.agent import app as governed_app
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load governed target fleet: {exc}",
        ) from exc

    fleet_context = _extract_fleet_context(governed_app)
    fleet_map = build_fleet_map(
        root_agent=fleet_context.get("root_agent"),
        tool_action_map=fleet_context.get("tool_action_map", {}),
    )
    return fleet_map.to_dict()


@router.post("/attack")
async def run_attack(request: AttackRequest) -> dict[str, Any]:
    """Execute a red-team attack against the governed fleet."""
    objective = OBJECTIVES.get(request.objective_id)
    if objective is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown objective_id '{request.objective_id}'",
        )

    # Import governed fleet App
    try:
        from agents.governed.agent import app as governed_app
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load governed target fleet: {exc}",
        ) from exc

    fleet_context = _extract_fleet_context(governed_app)

    if request.mode == "campaign":
        campaign = await execute_campaign(
            objective=objective,
            governed_app=governed_app,
            fleet_context=fleet_context,
            max_steps=request.max_steps,
        )

        has_allowed = any(r.verdict == "allowed" for r in campaign.results)
        aggregate_verdict = "allowed" if has_allowed else "blocked"

        max_blast_radius = None
        max_score = -1
        for r in campaign.results:
            if r.blast_radius and r.blast_radius.score > max_score:
                max_score = r.blast_radius.score
                max_blast_radius = r.blast_radius

        return {
            "campaign_id": campaign.id,
            "objective": {
                "id": objective.id,
                "name": objective.name,
                "description": objective.description,
                "injection_surface": objective.injection_surface,
            },
            "mode": "campaign",
            "status": campaign.status,
            "total_steps": len(campaign.results),
            "successful_steps": sum(
                1 for r in campaign.results if r.verdict == "allowed"
            ),
            "aggregate_verdict": aggregate_verdict,
            "steps": [
                {
                    "step_number": r.step.step_number,
                    "phase": r.step.phase,
                    "surface": r.step.surface,
                    "technique": r.step.technique,
                    "payload": r.step.payload,
                    "verdict": r.verdict,
                    "defense_layer": r.defense_layer,
                    "denial_reasons": r.denial_reasons,
                    "chain_id": r.chain_id,
                    "spans_count": r.spans_count,
                }
                for r in campaign.results
            ],
            "blast_radius": (
                dataclasses.asdict(max_blast_radius)
                if max_blast_radius is not None
                else None
            ),
        }

    # Default: single attack mode
    result = await execute_attack(
        objective=objective,
        governed_app=governed_app,
        fleet_context=fleet_context,
    )

    return {
        "objective": {
            "id": objective.id,
            "name": objective.name,
            "description": objective.description,
            "injection_surface": objective.injection_surface,
        },
        "payload": {
            "payload_text": result.payload.payload_text,
            "model_used": result.payload.model_used,
            "injection_surface": result.payload.injection_surface,
            "target_tool": result.payload.target_tool,
        },
        "verdict": result.verdict,
        "blocked_by": result.blocked_by,
        "chain_id": result.chain_id,
        "spans_count": result.spans_count,
        "denial_reasons": result.denial_reasons,
        "blast_radius": (
            dataclasses.asdict(result.blast_radius)
            if result.blast_radius is not None
            else None
        ),
    }
