"""Unit tests for red_team.narrative span emission helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from red_team.narrative import (
    emit_adapt_span,
    emit_complete_span,
    emit_generate_span,
    emit_inject_span,
    emit_plan_span,
    emit_recon_span,
    emit_result_span,
    emit_step_span,
)


def _mock_firestore() -> MagicMock:
    """Create a minimal Firestore mock that accepts writes."""
    db = MagicMock()
    db.collection.return_value.document.return_value = MagicMock()
    return db


# ---------------------------------------------------------------------------
# emit_recon_span
# ---------------------------------------------------------------------------


def test_emit_recon_span_agent_id_and_action() -> None:
    """Assert recon span uses red_team:recon agent_id and fleet_recon action."""
    fleet = SimpleNamespace(
        agent_count=22,
        tool_count=20,
        weakest_agents=lambda: ["uk_kyc_agent", "usa_kyc_agent"],
        boundary_agents=lambda: ["global_kyc_agent"],
    )
    with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
        span_id = emit_recon_span("chain-001", fleet)

    assert span_id is not None
    assert isinstance(span_id, str)
    assert len(span_id) > 0


def test_emit_recon_span_reason_content() -> None:
    """Assert recon reason includes agent count, tool count, and weakest agents."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    fleet = SimpleNamespace(
        agent_count=10,
        tool_count=5,
        weakest_agents=lambda: ["agent_a"],
        boundary_agents=list,
    )
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_recon_span("chain-recon", fleet)
    finally:
        unsubscribe_ws(capture)

    assert len(captured) == 1
    doc = captured[0]
    assert doc["agent_id"] == "red_team:recon"
    assert doc["action_requested"] == "fleet_recon"
    assert doc["decision"] == "allow"
    assert "10 agents" in doc["reason"]
    assert "5 tools" in doc["reason"]
    assert "agent_a" in doc["reason"]
    assert doc["chain_id"] == "chain-recon"


# ---------------------------------------------------------------------------
# emit_plan_span
# ---------------------------------------------------------------------------


def test_emit_plan_span_fields() -> None:
    """Assert plan span captures step count, techniques, and surfaces."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    plan = SimpleNamespace(
        steps=[
            SimpleNamespace(technique="instruction_override", surface="user_message"),
            SimpleNamespace(technique="encoding_evasion", surface="tool_response"),
        ]
    )
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_plan_span("chain-plan", plan, model_used="llama-4-maverick")
    finally:
        unsubscribe_ws(capture)

    assert len(captured) == 1
    doc = captured[0]
    assert doc["agent_id"] == "red_team:strategist"
    assert doc["action_requested"] == "plan_campaign"
    assert doc["decision"] == "allow"
    assert "2 step(s)" in doc["reason"]
    assert "llama-4-maverick" in doc["reason"]


# ---------------------------------------------------------------------------
# emit_generate_span
# ---------------------------------------------------------------------------


def test_emit_generate_span_flagged() -> None:
    """Assert generate span records model, objective, and screen result."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_generate_span(
                "chain-gen", "llama-3.3", "Scope Escalation", screen_flagged=True
            )
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:generator"
    assert doc["action_requested"] == "generate_payload"
    assert doc["decision"] == "allow"
    assert "llama-3.3" in doc["reason"]
    assert "Scope Escalation" in doc["reason"]
    assert "flagged" in doc["reason"]


def test_emit_generate_span_clean_fallback() -> None:
    """Assert generate span notes fallback when screen was clean."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_generate_span(
                "chain-gen2", "gemini-2.5-flash", "Exfiltrate", screen_flagged=False
            )
    finally:
        unsubscribe_ws(capture)

    assert "example_goal fallback" in captured[0]["reason"]


# ---------------------------------------------------------------------------
# emit_step_span
# ---------------------------------------------------------------------------


def test_emit_step_span_blocked() -> None:
    """Assert step span encodes all execution metadata for a blocked step."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_step_span(
                chain_id="chain-step",
                step_number=2,
                surface="tool_response",
                technique="encoding_evasion",
                target_tool="get_company_profile",
                target_agent="uk_kyc_agent",
                verdict="blocked",
                defense_layer="F5_model_armor",
                denial_reasons=["quarantined by Model Armor ML classifier"],
            )
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:executor"
    assert doc["action_requested"] == "execute_step"
    assert doc["decision"] == "deny"
    assert "Step 2" in doc["reason"]
    assert "tool_response" in doc["reason"]
    assert "encoding_evasion" in doc["reason"]
    assert "F5_model_armor" in doc["reason"]
    assert doc["defense_layer"] == "F5_model_armor"


def test_emit_step_span_allowed() -> None:
    """Assert step span uses decision=allow when verdict is allowed."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_step_span(
                chain_id="chain-pass",
                step_number=1,
                surface="user_message",
                technique=None,
                target_tool=None,
                target_agent=None,
                verdict="allowed",
                defense_layer=None,
            )
    finally:
        unsubscribe_ws(capture)

    assert captured[0]["decision"] == "allow"


# ---------------------------------------------------------------------------
# emit_adapt_span
# ---------------------------------------------------------------------------


def test_emit_adapt_span_content() -> None:
    """Assert adapt span records feedback and new technique/surface."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_adapt_span(
                chain_id="chain-adapt",
                feedback_signal="Blocked by regex.",
                new_technique="encoding_evasion",
                new_surface="tool_response",
            )
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:strategist"
    assert doc["action_requested"] == "adapt_step"
    assert "Blocked by regex" in doc["reason"]
    assert "encoding_evasion" in doc["reason"]
    assert "tool_response" in doc["reason"]


# ---------------------------------------------------------------------------
# emit_complete_span
# ---------------------------------------------------------------------------


def test_emit_complete_span_blocked() -> None:
    """Assert complete span records aggregate stats for a fully blocked campaign."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_complete_span(
                chain_id="chain-complete",
                total_steps=3,
                blocked_count=3,
                aggregate_verdict="blocked",
                max_blast_radius=7.2,
            )
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:executor"
    assert doc["action_requested"] == "campaign_complete"
    assert doc["decision"] == "deny"
    assert "3/3 steps blocked" in doc["reason"]
    assert "BLOCKED" in doc["reason"]
    assert "7.2" in doc["reason"]


def test_emit_complete_span_allowed() -> None:
    """Assert complete span uses allow decision when attack succeeded."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_complete_span("chain-pass", 2, 1, "allowed")
    finally:
        unsubscribe_ws(capture)

    assert captured[0]["decision"] == "allow"


# ---------------------------------------------------------------------------
# emit_inject_span
# ---------------------------------------------------------------------------


def test_emit_inject_span_with_tool() -> None:
    """Assert inject span records surface and target tool."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_inject_span("chain-inj", "tool_response", "get_company_profile")
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:executor"
    assert doc["action_requested"] == "inject_surface"
    assert "tool_response" in doc["reason"]
    assert "get_company_profile" in doc["reason"]


def test_emit_inject_span_user_message() -> None:
    """Assert inject span works for user_message surface without target tool."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_inject_span("chain-msg", "user_message", None)
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert "user_message" in doc["reason"]
    assert "->" not in doc["reason"]


# ---------------------------------------------------------------------------
# emit_result_span
# ---------------------------------------------------------------------------


def test_emit_result_span_blocked() -> None:
    """Assert result span encodes verdict, blocker, and blast radius."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_result_span("chain-res", "blocked", "F5_regex", 4.8, "MEDIUM")
    finally:
        unsubscribe_ws(capture)

    doc = captured[0]
    assert doc["agent_id"] == "red_team:executor"
    assert doc["action_requested"] == "attack_complete"
    assert doc["decision"] == "deny"
    assert "BLOCKED" in doc["reason"]
    assert "F5_regex" in doc["reason"]
    assert "4.8" in doc["reason"]
    assert "MEDIUM" in doc["reason"]


# ---------------------------------------------------------------------------
# Fail-safe behavior
# ---------------------------------------------------------------------------


def test_narrative_spans_swallow_firestore_failures() -> None:
    """Assert all emit helpers still return a span_id and never raise on Firestore failure.

    ``emit_span`` itself is fail-safe (swallows Firestore exceptions internally),
    so the narrative helpers return the span_id rather than None.  The key
    assertion is that no exception propagates to the caller.
    """
    boom_db = MagicMock()
    boom_db.collection.return_value.document.return_value.set.side_effect = (
        RuntimeError("Firestore unreachable")
    )

    fleet = SimpleNamespace(
        agent_count=1,
        tool_count=1,
        weakest_agents=list,
        boundary_agents=list,
    )
    plan = SimpleNamespace(steps=[])

    with patch("audit.trace._get_firestore_client", return_value=boom_db):
        # None of these should raise — they must return a valid span_id
        assert isinstance(emit_recon_span("c", fleet), str)
        assert isinstance(emit_plan_span("c", plan), str)
        assert isinstance(emit_generate_span("c", "m", "o", True), str)
        assert isinstance(
            emit_step_span("c", 1, "s", "t", None, None, "blocked", None), str
        )
        assert isinstance(emit_adapt_span("c", "fb", "t", "s"), str)
        assert isinstance(emit_complete_span("c", 1, 1, "blocked"), str)
        assert isinstance(emit_inject_span("c", "user_message", None), str)
        assert isinstance(emit_result_span("c", "blocked", None, None, None), str)


def test_narrative_spans_return_none_on_reason_building_error() -> None:
    """Assert emit helpers return None when reason-building itself fails.

    If the fleet_map object is completely broken (e.g. missing required
    attributes), the outer try/except in the narrative helper catches it.
    """
    broken_fleet = object()  # has no agent_count, weakest_agents, etc.

    with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
        assert emit_recon_span("c", broken_fleet) is None


# ---------------------------------------------------------------------------
# Chain ID passthrough
# ---------------------------------------------------------------------------


def test_all_spans_use_provided_chain_id() -> None:
    """Assert every emit helper passes the chain_id through to emit_span."""
    captured = []

    def capture(span_doc: dict) -> None:
        captured.append(span_doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(capture)
    fleet = SimpleNamespace(
        agent_count=1,
        tool_count=1,
        weakest_agents=list,
        boundary_agents=list,
    )
    plan = SimpleNamespace(steps=[])

    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_recon_span("shared-chain", fleet)
            emit_plan_span("shared-chain", plan)
            emit_generate_span("shared-chain", "m", "o", True)
            emit_step_span("shared-chain", 1, "s", "t", None, None, "blocked", None)
            emit_adapt_span("shared-chain", "fb", "t", "s")
            emit_complete_span("shared-chain", 1, 1, "blocked")
            emit_inject_span("shared-chain", "user_message", None)
            emit_result_span("shared-chain", "blocked", None, None, None)
    finally:
        unsubscribe_ws(capture)

    assert len(captured) == 8
    for doc in captured:
        assert doc["chain_id"] == "shared-chain"


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------


def test_narrative_spans_broadcast_to_ws_subscribers() -> None:
    """Assert narrative spans fire WebSocket broadcast via subscribe_ws."""
    received = []

    def ws_cb(doc: dict) -> None:
        received.append(doc)

    from audit.trace import subscribe_ws, unsubscribe_ws

    subscribe_ws(ws_cb)
    try:
        with patch("audit.trace._get_firestore_client", return_value=_mock_firestore()):
            emit_generate_span("ws-test", "model-x", "obj-y", True)
    finally:
        unsubscribe_ws(ws_cb)

    assert len(received) == 1
    assert received[0]["agent_id"] == "red_team:generator"
