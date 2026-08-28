"""Red-team attack executor: runs a generated payload against the governed fleet."""

import uuid
from dataclasses import dataclass
from typing import Any

from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

from audit.replay import derive_verdict, get_chain_spans
from blast.radius import BlastRadiusResult, compute_blast_radius

from .agent import AttackPayload, generate_payload
from .objectives import AttackObjective
from .poison_plugin import PoisonPlugin


@dataclass
class AttackResult:
    """Complete result of a red-team attack run."""

    objective_id: str
    payload: AttackPayload
    verdict: str  # "blocked" or "allowed"
    blocked_by: str | None  # "gateway_scope", "model_armor", or None if allowed
    chain_id: str | None
    blast_radius: BlastRadiusResult | None
    spans_count: int
    denial_reasons: list[str]


def _find_tool_owner_agent(agent: Any, target_tool: str) -> str | None:
    """Find the name of the agent in the hierarchy that owns the specified tool."""
    if agent is None:
        return None
    tools = getattr(agent, "tools", None) or []
    for tool in tools:
        tname = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if tname == target_tool:
            return getattr(agent, "name", None)
    for sub in getattr(agent, "sub_agents", None) or []:
        owner = _find_tool_owner_agent(sub, target_tool)
        if owner is not None:
            return owner
    return None


async def execute_attack(
    objective: AttackObjective,
    governed_app: App,
    fleet_context: dict[str, Any],
    clean_query: str = "Create a compliance report on Google UK Limited",
) -> AttackResult:
    """Execute a red-team attack against the governed fleet.

    Args:
        objective: Attack objective to execute.
        governed_app: The governed App with GatewayPlugin attached.
        fleet_context: Dict with "agent_names", "tool_names", "tool_action_map", "root_agent".
        clean_query: Legitimate query to use for tool_response injection.

    Returns:
        AttackResult with the full attack outcome.
    """
    payload = generate_payload(objective, fleet_context)

    chain_id = str(uuid.uuid4())
    session_id = f"session-redteam-{uuid.uuid4().hex[:8]}"
    user_id = "red-team-tester"
    app_name = "red_team_run"

    root_agent = fleet_context.get("root_agent") or governed_app.root_agent
    plugins = list(governed_app.plugins)

    if objective.injection_surface == "tool_response":
        target_tool = payload.target_tool or (
            objective.target_tools[0] if objective.target_tools else ""
        )
        poison_plugin = PoisonPlugin(
            target_tool=target_tool,
            poison_text=payload.payload_text,
        )
        plugins.insert(0, poison_plugin)
        message_text = clean_query
    else:
        message_text = payload.payload_text

    run_app = App(name=app_name, root_agent=root_agent, plugins=plugins)
    runner = InMemoryRunner(app=run_app)

    runner_error: str | None = None
    try:
        await runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        user_msg = types.Content(
            role="user",
            parts=[types.Part.from_text(text=message_text)],
        )
        async for _ in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            invocation_id=chain_id,
            new_message=user_msg,
        ):
            pass
    except Exception as exc:  # noqa: BLE001
        runner_error = f"runner_error: {type(exc).__name__}: {exc}"

    spans = get_chain_spans(chain_id)
    if runner_error and not spans:
        verdict = "error"
    else:
        verdict = derive_verdict(spans)
    denial_reasons = [s.reason for s in spans if s.decision == "deny"]
    if runner_error:
        denial_reasons.append(runner_error)

    blocked_by: str | None = None
    if verdict == "blocked":
        if any(
            s.decision == "deny" and s.action_requested.startswith("screen:")
            for s in spans
        ):
            blocked_by = "model_armor"
        else:
            blocked_by = "gateway_scope"

    # Determine injection agent for blast radius calculation
    injection_agent = getattr(root_agent, "name", "root_agent")
    if objective.injection_surface == "tool_response" and payload.target_tool:
        tool_owner = _find_tool_owner_agent(root_agent, payload.target_tool)
        if tool_owner:
            injection_agent = tool_owner

    blast_radius = compute_blast_radius(
        root_agent=root_agent,
        injection_agent=injection_agent,
        tool_action_map=fleet_context.get("tool_action_map", {}),
    )

    return AttackResult(
        objective_id=objective.id,
        payload=payload,
        verdict=verdict,
        blocked_by=blocked_by,
        chain_id=chain_id,
        blast_radius=blast_radius,
        spans_count=len(spans),
        denial_reasons=denial_reasons,
    )
