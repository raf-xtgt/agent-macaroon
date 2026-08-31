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
from .narrative import (
    emit_adapt_span,
    emit_complete_span,
    emit_generate_span,
    emit_inject_span,
    emit_plan_span,
    emit_recon_span,
    emit_result_span,
    emit_step_span,
)
from .objectives import AttackObjective
from .poison_plugin import PoisonPlugin
from .recon.fleet_map import FleetMap, build_fleet_map
from .strategy.campaign import Campaign, CampaignStep, StepResult
from .strategy.feedback import parse_defense_response
from .strategy.strategist import PlannedStep, adapt_step, plan_campaign
from .surfaces.inter_agent import prepare_inter_agent_surface
from .surfaces.state_injection import prepare_state_injection_surface
from .surfaces.tool_response import prepare_tool_response_surface
from .surfaces.user_message import prepare_user_message_surface


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


def _prepare_surface(
    step: CampaignStep,
    objective: AttackObjective,
    clean_query: str,
) -> dict[str, Any]:
    """Route a campaign step to the correct surface helper."""
    if step.surface == "tool_response":
        target_tool = step.target_tool or (
            objective.target_tools[0] if objective.target_tools else ""
        )
        return prepare_tool_response_surface(
            payload=step.payload,
            target_tool=target_tool,
            clean_query=clean_query,
        )

    if step.surface == "state_injection":
        return prepare_state_injection_surface(
            payload=step.payload,
            target_tool=step.target_tool or "",
            target_state_key=step.target_state_key or "injected_state",
            clean_query=clean_query,
        )

    if step.surface == "inter_agent":
        return prepare_inter_agent_surface(
            payload=step.payload,
            target_agent=step.target_agent or "",
            target_state_key=step.target_state_key or "injected_instruction",
            clean_query=clean_query,
        )

    return prepare_user_message_surface(payload=step.payload)


def extract_fleet_context(
    governed_app: App,
    fleet_map: FleetMap | None = None,
) -> dict[str, Any]:
    """Extract agent names, tool names, and action mappings from the governed App.

    Accepts an optional pre-built FleetMap to avoid redundant tree walks.
    """
    root_agent = getattr(governed_app, "root_agent", None)

    tool_action_map: dict[str, str] = {}
    for plugin in getattr(governed_app, "plugins", []):
        if hasattr(plugin, "_tool_action_map"):
            tool_action_map = plugin._tool_action_map
            break

    if fleet_map is None:
        fleet_map = build_fleet_map(
            root_agent=root_agent, tool_action_map=tool_action_map
        )

    unique_tools: set[str] = set()
    for meta in fleet_map.agents.values():
        for t in meta.get("tools", []):
            unique_tools.add(t)

    return {
        "agent_names": list(fleet_map.agents.keys()),
        "tool_names": sorted(unique_tools),
        "tool_action_map": tool_action_map,
        "root_agent": root_agent,
        "fleet_map": fleet_map,
    }


async def execute_attack(
    objective: AttackObjective,
    governed_app: App,
    fleet_context: dict[str, Any],
    clean_query: str = "Create a compliance report on Google UK Limited",
) -> AttackResult:
    """Execute a single-shot red-team attack against the governed fleet."""
    payload = generate_payload(objective, fleet_context)

    chain_id = str(uuid.uuid4())

    # --- Narrative: GENERATE span ---
    screen_flagged = "+example_goal" not in payload.model_used
    emit_generate_span(chain_id, payload.model_used, objective.name, screen_flagged)
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

    # --- Narrative: INJECT span ---
    inject_tool = (
        payload.target_tool if objective.injection_surface == "tool_response" else None
    )
    emit_inject_span(chain_id, objective.injection_surface, inject_tool)

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

    # --- Narrative: RESULT span ---
    br_score = getattr(blast_radius, "score", None)
    br_level = getattr(blast_radius, "max_sensitivity", None)
    emit_result_span(chain_id, verdict, blocked_by, br_score, br_level)

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
    message_text = (
        clean_query
        if step.surface in ("tool_response", "state_injection", "inter_agent")
        else step.payload
    )

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

    Maintains a single persistent ADK session across attack steps. Each step
    is routed through the correct injection surface via the surfaces/ helpers.
    """
    root_agent = fleet_context.get("root_agent") or governed_app.root_agent
    tool_action_map = fleet_context.get("tool_action_map", {})

    fleet_map = fleet_context.get("fleet_map") or build_fleet_map(
        root_agent, tool_action_map=tool_action_map
    )
    catalog = load_all_templates()

    # Narrative chain ID shared by all narrative spans for this campaign.
    narrative_chain_id = f"campaign-narrative-{uuid.uuid4().hex[:8]}"

    # --- Narrative: RECON span ---
    emit_recon_span(narrative_chain_id, fleet_map)

    initial_plan = await plan_campaign(objective.id, fleet_map, catalog)

    # --- Narrative: PLAN span ---
    emit_plan_span(narrative_chain_id, initial_plan)

    campaign = Campaign(
        id=f"campaign-{uuid.uuid4().hex[:8]}",
        objective=objective.id,
        fleet_map=fleet_map,
        max_steps=max_steps,
    )

    user_id = "red-team-tester"
    app_name = "red_team_campaign"
    plugins = list(governed_app.plugins)

    steps_queue: list[PlannedStep] = list(initial_plan.steps)
    step_num = 1

    while step_num <= max_steps and steps_queue:
        planned = steps_queue.pop(0)

        # Force the objective's injection surface when the strategist picks
        # user_message for an objective that needs tool_response injection.
        # Without this, PoisonPlugin never fires and F5 never screens.
        effective_surface = planned.surface
        if (
            objective.injection_surface == "tool_response"
            and planned.surface == "user_message"
        ):
            effective_surface = "tool_response"

        effective_tool = planned.target_tool or (
            objective.target_tools[0] if objective.target_tools else None
        )

        campaign_step = CampaignStep(
            step_number=step_num,
            phase=planned.phase,
            objective=objective.id,
            surface=effective_surface,
            payload=planned.payload_template,
            template_id=objective.id,
            technique=planned.technique,
            target_agent=planned.target_agent,
            target_tool=effective_tool,
        )
        campaign.steps.append(campaign_step)

        surface_config = _prepare_surface(campaign_step, objective, clean_query)
        surface_plugin = surface_config.get("plugin")

        # Build a fresh plugin list for this step
        step_plugins = [p for p in plugins if not isinstance(p, PoisonPlugin)]
        if surface_plugin is not None:
            step_plugins.insert(0, surface_plugin)

        # Create a fresh App + Runner for this step so PoisonPlugin takes effect
        step_app = App(name=app_name, root_agent=root_agent, plugins=step_plugins)
        step_runner = InMemoryRunner(app=step_app)
        step_session_id = f"session-campaign-step-{step_num}-{uuid.uuid4().hex[:8]}"

        try:
            await step_runner.session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=step_session_id,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to create step session: {exc}")

        step_result = await _execute_step_in_session(
            step=campaign_step,
            runner=step_runner,
            session_id=step_session_id,
            user_id=user_id,
            root_agent=root_agent,
            tool_action_map=tool_action_map,
            clean_query=clean_query,
        )
        campaign.add_step_result(step_result)

        # --- Narrative: STEP span ---
        emit_step_span(
            chain_id=narrative_chain_id,
            step_number=step_num,
            surface=campaign_step.surface,
            technique=campaign_step.technique,
            target_tool=campaign_step.target_tool,
            target_agent=campaign_step.target_agent,
            verdict=step_result.verdict,
            defense_layer=step_result.defense_layer,
            denial_reasons=step_result.denial_reasons,
        )

        if step_result.verdict == "allowed" or step_num >= max_steps:
            break

        if not steps_queue:
            adapted = await adapt_step(campaign, step_result)
            if adapted:
                # --- Narrative: ADAPT span ---
                signal = parse_defense_response(step_result)
                emit_adapt_span(
                    chain_id=narrative_chain_id,
                    feedback_signal=f"Blocked by {signal.blocked_by or 'unknown'}.",
                    new_technique=adapted.technique,
                    new_surface=adapted.surface,
                )
                steps_queue.append(adapted)

        step_num += 1

    # --- Narrative: COMPLETE span ---
    blocked_count = sum(1 for r in campaign.results if r.verdict == "blocked")
    total_steps = len(campaign.results)
    agg_verdict = (
        "allowed"
        if any(r.verdict == "allowed" for r in campaign.results)
        else "blocked"
    )
    max_br: float | None = None
    for r in campaign.results:
        if r.blast_radius is not None:
            score = getattr(r.blast_radius, "score", None)
            if score is not None and (max_br is None or score > max_br):
                max_br = score
    emit_complete_span(
        narrative_chain_id, total_steps, blocked_count, agg_verdict, max_br
    )

    return campaign
