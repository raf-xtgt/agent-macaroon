"""FastAPI router for red-team attack endpoints."""

import dataclasses
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .executor import execute_attack
from .objectives import OBJECTIVES

router = APIRouter(prefix="/red-team", tags=["red-team"])


class AttackRequest(BaseModel):
    """Request model for initiating a red-team attack."""

    objective_id: str


def _extract_fleet_context(governed_app: Any) -> dict[str, Any]:
    """Extract agent names, tool names, and action mappings from the governed App."""
    root_agent = getattr(governed_app, "root_agent", None)
    agent_names: list[str] = []
    tool_names_set: set[str] = set()

    if root_agent is not None:
        queue = [root_agent]
        visited: set[str] = set()
        while queue:
            curr = queue.pop(0)
            name = getattr(curr, "name", None) or getattr(curr, "__name__", None)
            if name and name not in visited:
                visited.add(name)
                agent_names.append(name)
                for tool in getattr(curr, "tools", None) or []:
                    tname = getattr(tool, "name", None) or getattr(
                        tool, "__name__", None
                    )
                    if tname:
                        tool_names_set.add(tname)
                for sub in getattr(curr, "sub_agents", None) or []:
                    if sub is not None:
                        queue.append(sub)

    tool_action_map: dict[str, str] = {}
    for plugin in getattr(governed_app, "plugins", []):
        if hasattr(plugin, "_tool_action_map"):
            tool_action_map = plugin._tool_action_map
            break

    return {
        "agent_names": agent_names,
        "tool_names": sorted(tool_names_set),
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
