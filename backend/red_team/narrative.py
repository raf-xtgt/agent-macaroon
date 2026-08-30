"""Red-team narrative span emission helpers.

Thin wrappers around ``audit.trace.emit_span()`` that encode the red-team
naming conventions (``agent_id`` prefix ``red_team:*``, deterministic
``action_requested`` values) so the frontend can filter and render an attack
narrative timeline.

All emission calls are fail-safe: exceptions are swallowed to ensure narrative
instrumentation never alters attack execution or gateway decisions.
"""

from __future__ import annotations

from typing import Any

from audit.trace import emit_span

# ---------------------------------------------------------------------------
# Campaign-mode helpers
# ---------------------------------------------------------------------------


def emit_recon_span(chain_id: str, fleet_map: Any) -> str | None:
    """Emit a RECON narrative span summarising fleet reconnaissance.

    Args:
        chain_id: Shared attack chain ID.
        fleet_map: :class:`FleetMap` instance (or any object with
            ``agent_count``, ``tool_count``, ``weakest_agents()``,
            ``boundary_agents()``).

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        weakest = fleet_map.weakest_agents()[:3]
        boundaries = fleet_map.boundary_agents()
        reason = (
            f"Scanned {fleet_map.agent_count} agents, {fleet_map.tool_count} tools. "
            f"Weakest ceiling: {', '.join(weakest) if weakest else 'none'}. "
            f"Boundary agents: {', '.join(boundaries) if boundaries else 'none'}."
        )
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:recon",
            macaroon_identifier_hash=None,
            action_requested="fleet_recon",
            decision="allow",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_plan_span(
    chain_id: str,
    plan: Any,
    model_used: str | None = None,
) -> str | None:
    """Emit a PLAN narrative span after the strategist formulates a campaign.

    Args:
        chain_id: Shared attack chain ID.
        plan: :class:`CampaignPlan` (has ``.steps`` list of
            :class:`PlannedStep`).
        model_used: Model identifier used for planning.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        steps = getattr(plan, "steps", [])
        techniques = sorted({getattr(s, "technique", "unknown") for s in steps})
        surfaces = sorted({getattr(s, "surface", "unknown") for s in steps})
        planner = model_used or "unknown"
        reason = (
            f"{planner} planned {len(steps)} step(s). "
            f"Techniques: {', '.join(techniques)}. "
            f"Surfaces: {', '.join(surfaces)}."
        )
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:strategist",
            macaroon_identifier_hash=None,
            action_requested="plan_campaign",
            decision="allow",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_step_span(
    chain_id: str,
    step_number: int,
    surface: str,
    technique: str | None,
    target_tool: str | None,
    target_agent: str | None,
    verdict: str,
    defense_layer: str | None,
    denial_reasons: list[str] | None = None,
) -> str | None:
    """Emit a STEP narrative span after a campaign step executes.

    Args:
        chain_id: Shared attack chain ID.
        step_number: 1-based step index.
        surface: Injection surface used.
        technique: Evasion technique applied.
        target_tool: Tool targeted (may be *None*).
        target_agent: Agent targeted (may be *None*).
        verdict: ``"blocked"`` or ``"allowed"``.
        defense_layer: Which defense stopped it (e.g. ``"F5_regex"``).
        denial_reasons: Raw denial reason strings from defense spans.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        parts = [f"Step {step_number}"]
        parts.append(f"surface={surface}")
        if technique:
            parts.append(f"technique={technique}")
        if target_tool:
            parts.append(f"target_tool={target_tool}")
        if target_agent:
            parts.append(f"target_agent={target_agent}")
        parts.append(f"verdict={verdict}")
        if defense_layer:
            parts.append(f"defense={defense_layer}")
        if denial_reasons:
            parts.append(f"reasons=[{'; '.join(denial_reasons[:3])}]")
        reason = ". ".join(parts) + "."
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:executor",
            macaroon_identifier_hash=None,
            action_requested="execute_step",
            decision="allow" if verdict == "allowed" else "deny",
            reason=reason,
            defense_layer=defense_layer,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_adapt_span(
    chain_id: str,
    feedback_signal: str,
    new_technique: str | None,
    new_surface: str | None,
) -> str | None:
    """Emit an ADAPT narrative span after the strategist adjusts course.

    Args:
        chain_id: Shared attack chain ID.
        feedback_signal: Human-readable summary of the defense feedback
            (e.g. ``"Blocked by regex"``).
        new_technique: Adapted technique for the next step.
        new_surface: Adapted injection surface for the next step.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        reason = (
            f"{feedback_signal} "
            f"Switching to technique={new_technique or 'unchanged'}, "
            f"surface={new_surface or 'unchanged'}."
        )
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:strategist",
            macaroon_identifier_hash=None,
            action_requested="adapt_step",
            decision="allow",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_complete_span(
    chain_id: str,
    total_steps: int,
    blocked_count: int,
    aggregate_verdict: str,
    max_blast_radius: float | None = None,
) -> str | None:
    """Emit a COMPLETE narrative span when a campaign finishes.

    Args:
        chain_id: Shared attack chain ID.
        total_steps: Total steps executed.
        blocked_count: How many steps were blocked.
        aggregate_verdict: ``"blocked"`` or ``"allowed"``.
        max_blast_radius: Peak blast-radius score across steps.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        br_part = (
            f" Max blast radius: {max_blast_radius}."
            if max_blast_radius is not None
            else ""
        )
        reason = (
            f"{blocked_count}/{total_steps} steps blocked. "
            f"Aggregate verdict: {aggregate_verdict.upper()}.{br_part}"
        )
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:executor",
            macaroon_identifier_hash=None,
            action_requested="campaign_complete",
            decision="allow" if aggregate_verdict == "allowed" else "deny",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Single-mode helpers
# ---------------------------------------------------------------------------


def emit_generate_span(
    chain_id: str,
    model_used: str,
    objective_name: str,
    screen_flagged: bool,
) -> str | None:
    """Emit a GENERATE narrative span after payload generation.

    Args:
        chain_id: Shared attack chain ID.
        model_used: Model that produced the payload.
        objective_name: Human-readable objective name.
        screen_flagged: Whether the regex pre-screen flagged the payload.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        screen_status = (
            "flagged" if screen_flagged else "clean (using example_goal fallback)"
        )
        reason = (
            f'{model_used} produced payload for "{objective_name}". '
            f"Regex pre-screen: {screen_status}."
        )
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:generator",
            macaroon_identifier_hash=None,
            action_requested="generate_payload",
            decision="allow",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_inject_span(
    chain_id: str,
    surface: str,
    target_tool: str | None,
) -> str | None:
    """Emit an INJECT narrative span when the payload is placed on a surface.

    Args:
        chain_id: Shared attack chain ID.
        surface: Injection surface (``"user_message"`` or ``"tool_response"``).
        target_tool: Target tool for tool_response injection.

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        tool_part = f" -> {target_tool}" if target_tool else ""
        reason = f"surface: {surface}{tool_part}."
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:executor",
            macaroon_identifier_hash=None,
            action_requested="inject_surface",
            decision="allow",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None


def emit_result_span(
    chain_id: str,
    verdict: str,
    blocked_by: str | None,
    blast_radius_score: float | None,
    blast_radius_level: str | None,
) -> str | None:
    """Emit a RESULT narrative span after single-mode attack completes.

    Args:
        chain_id: Shared attack chain ID.
        verdict: ``"blocked"`` or ``"allowed"``.
        blocked_by: Defense layer that blocked (or *None*).
        blast_radius_score: Numerical score.
        blast_radius_level: Sensitivity level (``"HIGH"``/``"MEDIUM"``/``"LOW"``).

    Returns:
        The generated ``span_id``, or *None* on failure.
    """
    try:
        parts = [verdict.upper()]
        if blocked_by:
            parts.append(f"by {blocked_by}")
        if blast_radius_score is not None:
            br = f"Blast radius: {blast_radius_score}"
            if blast_radius_level:
                br += f" ({blast_radius_level})"
            parts.append(br)
        reason = ". ".join(parts) + "."
        return emit_span(
            chain_id=chain_id,
            parent_span_id=None,
            agent_id="red_team:executor",
            macaroon_identifier_hash=None,
            action_requested="attack_complete",
            decision="allow" if verdict == "allowed" else "deny",
            reason=reason,
        )
    except Exception:  # noqa: BLE001
        return None
