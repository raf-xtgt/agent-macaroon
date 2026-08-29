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
from .catalog.templates import load_all_templates
from .objectives import AttackObjective
from .poison_plugin import PoisonPlugin
from .recon.fleet_map import build_fleet_map
from .strategy.campaign import Campaign, CampaignStep, StepResult
from .strategy.strategist import PlannedStep, adapt_step, plan_campaign


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


async def _execute_step_in_session(
    step: CampaignStep,
    runner: InMemoryRunner,
    session_id: str,
    user_id: str,
    root_agent: Any,
    tool_action_map: dict[str, str],
    clean_query: str = "Create a compliance report on Google UK Limited",
) -> StepResult:
    """Execute a single campaign step within an existing persistent runner session."""
    chain_id = str(uuid.uuid4())
    message_text = clean_query if step.surface == "tool_response" else step.payload

    runner_error: str | None = None
    try:
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

    defense_layer: str | None = None
    if verdict == "blocked":
        if any(
            s.decision == "deny" and s.action_requested.startswith("screen:")
            for s in spans
        ):
            defense_layer = "F5_model_armor"
        else:
            defense_layer = "F4_gateway"

    injection_agent = step.target_agent or getattr(root_agent, "name", "root_agent")
    if step.surface == "tool_response" and step.target_tool:
        tool_owner = _find_tool_owner_agent(root_agent, step.target_tool)
        if tool_owner:
            injection_agent = tool_owner

    blast_radius = compute_blast_radius(
        root_agent=root_agent,
        injection_agent=injection_agent,
        tool_action_map=tool_action_map,
    )

    return StepResult(
        step=step,
        verdict=verdict,
        denial_reasons=denial_reasons,
        defense_layer=defense_layer,
        blast_radius=blast_radius,
        spans_count=len(spans),
        chain_id=chain_id,
    )


async def execute_campaign(
    objective: AttackObjective,
    governed_app: App,
    fleet_context: dict[str, Any],
    max_steps: int = 5,
    clean_query: str = "Create a compliance report on Google UK Limited",
) -> Campaign:
    """Execute a multi-step adversary campaign against the governed fleet.

    Maintains a single persistent ADK session across attack steps to test multi-turn
    conversational injection, defense evasion, and behavioral adaptation.

    Args:
        objective: The attack objective to pursue.
        governed_app: The governed App with GatewayPlugin attached.
        fleet_context: Dict with agent metadata and tool action maps.
        max_steps: Maximum number of steps in the campaign.
        clean_query: Legitimate query used for tool_response testing.

    Returns:
        Campaign: The completed campaign record with all step results.
    """
    root_agent = fleet_context.get("root_agent") or governed_app.root_agent
    tool_action_map = fleet_context.get("tool_action_map", {})

    fleet_map = build_fleet_map(root_agent, tool_action_map=tool_action_map)
    catalog = load_all_templates()

    # Formulate initial strategic plan
    initial_plan = await plan_campaign(objective.id, fleet_map, catalog)

    campaign = Campaign(
        id=f"campaign-{uuid.uuid4().hex[:8]}",
        objective=objective.id,
        fleet_map=fleet_map,
        max_steps=max_steps,
    )

    session_id = f"session-campaign-{uuid.uuid4().hex[:8]}"
    user_id = "red-team-tester"
    app_name = "red_team_campaign"

    plugins = list(governed_app.plugins)
    run_app = App(name=app_name, root_agent=root_agent, plugins=plugins)
    runner = InMemoryRunner(app=run_app)

    try:
        await runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to create campaign session: {exc}")

    steps_queue: list[PlannedStep] = list(initial_plan.steps)
    step_num = 1

    while step_num <= max_steps and steps_queue:
        planned = steps_queue.pop(0)
        campaign_step = CampaignStep(
            step_number=step_num,
            phase=planned.phase,
            objective=objective.id,
            surface=planned.surface,
            payload=planned.payload_template,
            template_id=objective.id,
            technique=planned.technique,
            target_agent=planned.target_agent,
            target_tool=planned.target_tool,
        )
        campaign.steps.append(campaign_step)

        # Set up dynamic PoisonPlugin if the step targets tool_response
        if planned.surface == "tool_response":
            target_tool = planned.target_tool or (
                objective.target_tools[0] if objective.target_tools else ""
            )
            poison_plugin = PoisonPlugin(
                target_tool=target_tool,
                poison_text=planned.payload_template,
            )
            # Prepend plugin to runner's app
            run_app.plugins = [
                poison_plugin,
                *[p for p in plugins if not isinstance(p, PoisonPlugin)],
            ]

        step_result = await _execute_step_in_session(
            step=campaign_step,
            runner=runner,
            session_id=session_id,
            user_id=user_id,
            root_agent=root_agent,
            tool_action_map=tool_action_map,
            clean_query=clean_query,
        )
        campaign.add_step_result(step_result)

        # Early exit if objective was achieved
        if step_result.verdict == "allowed" or step_num >= max_steps:
            break

        # If more steps are needed and queue is empty, adapt next step
        if not steps_queue:
            adapted = await adapt_step(campaign, step_result)
            if adapted:
                steps_queue.append(adapted)

        step_num += 1

    return campaign
