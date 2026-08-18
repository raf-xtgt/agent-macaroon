"""Unit tests for the framework-agnostic Gateway policy decision point."""

import hashlib
from datetime import datetime, timedelta, timezone

from gateway.policy import evaluate
from macaroon.attenuate import attenuate
from macaroon.issue import issue_root_macaroon
from registry.agents_registry import AgentRegistry


def test_allow_valid_delegated_macaroon() -> None:
    """Assert a valid, properly attenuated macaroon is allowed when within registry ceiling."""
    root_key = b"test-root-key-super-secret"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read and delete records",
        initial_scope={"read", "delete"},
        root_key=root_key,
        chain_id="chain-uuid-1234",
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    decision = evaluate(
        macaroon=delegated,
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert decision.requested_action == "read"
    assert decision.presenting_agent_id == "tool_caller_agent"
    assert decision.chain_id == "chain-uuid-1234"
    assert decision.macaroon_identifier_hash is not None
    assert (
        decision.macaroon_identifier_hash
        == hashlib.sha256(delegated.identifier.encode("utf-8")).hexdigest()
    )


def test_deny_no_macaroon() -> None:
    """Assert calling evaluate with None macaroon returns a fail-closed denial."""
    root_key = b"test-root-key"
    registry = AgentRegistry()

    decision = evaluate(
        macaroon=None,
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is False
    assert "no macaroon presented" in decision.reason
    assert decision.macaroon_identifier_hash is None
    assert decision.chain_id is None


def test_deny_tampered_macaroon() -> None:
    """Assert a macaroon with tampered caveats fails signature verification."""
    root_key = b"test-root-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read record",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    tampered = delegated.copy()
    tampered.caveats[0].caveat_id = "scope=delete,read"

    decision = evaluate(
        macaroon=tampered,
        requested_action="delete",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is False
    assert "signature verification failed" in decision.reason


def test_deny_out_of_scope() -> None:
    """Assert requesting an action outside the macaroon scope fails with standard reason."""
    root_key = b"test-root-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read only",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    decision = evaluate(
        macaroon=delegated,
        requested_action="delete",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is False
    assert decision.reason == "scope caveat violated: requested=delete, allowed=read"


def test_registry_ceiling_backstop_overrides_stale_macaroon_scope() -> None:
    """Assert live registry ceiling overrides a stale macaroon whose caveats still allow action."""
    root_key = b"test-root-key"
    registry = AgentRegistry()
    # 1. Agent initially has delete permission
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read and delete",
        initial_scope={"read", "delete"},
        root_key=root_key,
    )
    # 2. Macaroon is delegated with delete in scope
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"delete"},
        registry=registry,
    )

    # 3. Later, security tightens agent ceiling, revoking delete
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read"},
        owner="sec-team",
    )

    # 4. Presenting agent presents the stale macaroon requesting delete
    decision = evaluate(
        macaroon=delegated,
        requested_action="delete",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    # Must be denied at Step 2 despite macaroon cryptographic check passing
    assert decision.allowed is False
    assert "agent registry ceiling exceeded" in decision.reason
    assert "requested=delete" in decision.reason
    assert "allowed_by_ceiling=read" in decision.reason


def test_deny_under_chaos() -> None:
    """Assert evaluate catches registry or unexpected exceptions and fails closed."""
    root_key = b"test-root-key"

    class FailingRegistry(AgentRegistry):
        def ceiling(self, agent_id: str) -> frozenset[str]:
            raise RuntimeError("Database connection timed out")

    registry = FailingRegistry()
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )

    decision = evaluate(
        macaroon=macaroon,
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is False
    assert "gateway evaluation error (fail-closed)" in decision.reason
    assert "Database connection timed out" in decision.reason


def test_no_secret_leakage() -> None:
    """Assert root key bytes never appear in any GatewayDecision field or in its repr."""
    root_key = b"secret-token-key-material-999"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )

    # Allow decision
    allow_decision = evaluate(
        macaroon=macaroon,
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    # Deny decision
    deny_decision = evaluate(
        macaroon=macaroon,
        requested_action="delete",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
    )

    for decision in (allow_decision, deny_decision):
        assert root_key not in repr(decision).encode("utf-8")
        assert root_key.decode("utf-8", errors="ignore") not in repr(decision)
        for field_name in (
            "reason",
            "requested_action",
            "presenting_agent_id",
            "macaroon_identifier_hash",
            "chain_id",
        ):
            val = getattr(decision, field_name)
            if val is not None:
                assert root_key not in str(val).encode("utf-8")


def test_deny_expired_macaroon() -> None:
    """Assert an expired macaroon is denied by the Gateway."""
    root_key = b"test-root-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read"},
        owner="sec-team",
    )

    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
        expires_in_minutes=5,
    )

    # Evaluate 10 minutes later
    decision = evaluate(
        macaroon=macaroon,
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        root_key=root_key,
        registry=registry,
        current_time=now + timedelta(minutes=10),
    )

    assert decision.allowed is False
    assert "macaroon expired" in decision.reason


def test_deny_agent_mismatch() -> None:
    """Assert presenting agent mismatch with macaroon caveat is denied."""
    root_key = b"test-root-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read"},
        owner="sec-team",
    )
    registry.register(
        agent_id="unauthorized_agent",
        display_name="Unauthorized",
        max_scope={"read"},
        owner="sec-team",
    )

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    decision = evaluate(
        macaroon=delegated,
        requested_action="read",
        presenting_agent_id="unauthorized_agent",
        root_key=root_key,
        registry=registry,
    )

    assert decision.allowed is False
    assert "agent caveat violated" in decision.reason
