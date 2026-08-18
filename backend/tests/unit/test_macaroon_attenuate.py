"""Unit tests for caveat attenuation and scope narrowing (F2)."""

from datetime import datetime, timezone

import pytest

from macaroon.attenuate import (
    DelegationDepthExceededError,
    attenuate,
    current_scope,
)
from macaroon.issue import issue_root_macaroon
from macaroon.verify import (
    VerificationContext,
    verify_macaroon,
    verify_signature,
)
from registry.agents_registry import AgentRegistry


def test_current_scope_public_helper() -> None:
    """Assert current_scope extracts the latest scope caveat as a frozenset."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher",
        max_scope={"read", "fetch"},
        owner="team",
    )

    root = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Testing current_scope",
        initial_scope={"read", "write", "fetch"},
        root_key=root_key,
    )

    # Root scope
    assert current_scope(root) == frozenset({"fetch", "read", "write"})

    # Attenuated scope
    hop1 = attenuate(root, "researcher_agent", {"read", "fetch"}, registry)
    assert current_scope(hop1) == frozenset({"fetch", "read"})


def test_two_hop_narrowing_delegation_chain() -> None:
    """Assert multi-hop attenuation strictly narrows scope along the delegation chain."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher Specialist",
        max_scope={"read", "fetch", "write"},
        owner="research-team",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Execution Leaf",
        max_scope={"read"},
        owner="execution-team",
    )

    # 1. Orchestrator issues root macaroon with full permissions
    root_macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Quarterly Audit",
        initial_scope={"read", "write", "delete"},
        root_key=root_key,
        max_depth=5,
    )

    # 2. Hop 1: Orchestrator -> Researcher
    # Researcher requests {"read", "fetch"}. Current={"read", "write", "delete"}, Ceiling={"read", "fetch", "write"}
    # Expected: {"read", "fetch"} & {"read", "write", "delete"} & {"read", "fetch", "write"} = {"read"}
    # Note: "fetch" was not in root scope, so it is filtered out. Resulting scope is {"read"}.
    hop1_macaroon = attenuate(
        macaroon=root_macaroon,
        to_agent_id="researcher_agent",
        task_required_scope={"read", "fetch"},
        registry=registry,
    )

    # Verify Hop 1 caveats and signature
    assert verify_signature(hop1_macaroon, root_key) is True
    ctx_researcher = VerificationContext(
        requested_action="read",
        presenting_agent_id="researcher_agent",
        current_time=datetime.now(timezone.utc),
    )
    res1 = verify_macaroon(hop1_macaroon, root_key, ctx_researcher)
    assert res1.passed is True

    # 3. Hop 2: Researcher -> Tool Caller
    # Tool caller requests {"read", "delete"}. Current={"read"}, Ceiling={"read"}
    # Expected: {"read"} (delete is blocked because it was excluded upstream)
    hop2_macaroon = attenuate(
        macaroon=hop1_macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read", "delete"},
        registry=registry,
    )

    assert verify_signature(hop2_macaroon, root_key) is True
    ctx_tool_caller_read = VerificationContext(
        requested_action="read",
        presenting_agent_id="tool_caller_agent",
        current_time=datetime.now(timezone.utc),
    )
    res2_read = verify_macaroon(hop2_macaroon, root_key, ctx_tool_caller_read)
    assert res2_read.passed is True

    # Confirm "delete" is denied even though tool caller requested it
    ctx_tool_caller_delete = VerificationContext(
        requested_action="delete",
        presenting_agent_id="tool_caller_agent",
        current_time=datetime.now(timezone.utc),
    )
    res2_delete = verify_macaroon(hop2_macaroon, root_key, ctx_tool_caller_delete)
    assert res2_delete.passed is False
    assert res2_delete.reason == "scope caveat violated: requested=delete, allowed=read"


def test_cannot_widen_scope_by_requesting_superset() -> None:
    """Assert requesting a superset never expands beyond current scope."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="worker_agent",
        display_name="Worker",
        max_scope={"read", "write", "delete", "admin"},
        owner="worker-team",
    )

    root_macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Read only operation",
        initial_scope={"read"},
        root_key=root_key,
    )

    # Worker attempts to expand scope to include write and delete
    attenuated = attenuate(
        macaroon=root_macaroon,
        to_agent_id="worker_agent",
        task_required_scope={"read", "write", "delete"},
        registry=registry,
    )

    ctx_write = VerificationContext(
        requested_action="write",
        presenting_agent_id="worker_agent",
        current_time=datetime.now(timezone.utc),
    )
    res = verify_macaroon(attenuated, root_key, ctx_write)
    assert res.passed is False
    assert res.reason == "scope caveat violated: requested=write, allowed=read"


def test_prd_f3_registry_ceiling_enforcement() -> None:
    """PRD F3: upstream has write, downstream requests write, but ceiling is read-only -> write excluded."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="readonly_tool_caller",
        display_name="Read Only Leaf",
        max_scope={"read"},
        owner="security-team",
    )

    root_macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Write operation",
        initial_scope={"read", "write"},
        root_key=root_key,
    )

    attenuated = attenuate(
        macaroon=root_macaroon,
        to_agent_id="readonly_tool_caller",
        task_required_scope={"read", "write"},
        registry=registry,
    )

    ctx_write = VerificationContext(
        requested_action="write",
        presenting_agent_id="readonly_tool_caller",
        current_time=datetime.now(timezone.utc),
    )
    res = verify_macaroon(attenuated, root_key, ctx_write)
    assert res.passed is False
    assert res.reason == "scope caveat violated: requested=write, allowed=read"


def test_delegation_depth_exhaustion_raises_error() -> None:
    """Assert exceeding max_depth raises DelegationDepthExceededError and stops delegation."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="agent_hop_1",
        display_name="Hop 1 Agent",
        max_scope={"read"},
        owner="team-1",
    )
    registry.register(
        agent_id="agent_hop_2",
        display_name="Hop 2 Agent",
        max_scope={"read"},
        owner="team-2",
    )

    # Issue with max_depth=1
    macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Single hop task",
        initial_scope={"read"},
        root_key=root_key,
        max_depth=1,
    )

    # First hop decrements max_depth: 1 -> 0 (should succeed)
    hop1 = attenuate(
        macaroon=macaroon,
        to_agent_id="agent_hop_1",
        task_required_scope={"read"},
        registry=registry,
    )

    # Second hop sees remaining_depth=0 and must raise DelegationDepthExceededError
    with pytest.raises(DelegationDepthExceededError) as exc_info:
        attenuate(
            macaroon=hop1,
            to_agent_id="agent_hop_2",
            task_required_scope={"read"},
            registry=registry,
        )
    assert "remaining delegation depth is 0" in str(exc_info.value)


def test_empty_resulting_scope_authorizes_nothing() -> None:
    """Assert disjoint intersection produces an empty scope caveat that authorizes nothing."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="delete_worker",
        display_name="Delete Worker",
        max_scope={"delete"},
        owner="cleanup-team",
    )

    root_macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )

    # Intersection of {"read"} and {"delete"} is empty
    empty_scope_macaroon = attenuate(
        macaroon=root_macaroon,
        to_agent_id="delete_worker",
        task_required_scope={"delete"},
        registry=registry,
    )

    assert verify_signature(empty_scope_macaroon, root_key) is True
    ctx = VerificationContext(
        requested_action="delete",
        presenting_agent_id="delete_worker",
        current_time=datetime.now(timezone.utc),
    )
    res = verify_macaroon(empty_scope_macaroon, root_key, ctx)
    assert res.passed is False
    assert res.reason == "scope caveat violated: requested=delete, allowed="


def test_two_hop_tampered_macaroon_fails_verification() -> None:
    """Assert that a 2-hop attenuated macaroon fails verification if any caveat is tampered with."""
    root_key = b"enterprise-hmac-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher",
        max_scope={"read", "fetch"},
        owner="team-1",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read"},
        owner="team-2",
    )

    root = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Multi-hop task",
        initial_scope={"read", "fetch"},
        root_key=root_key,
    )
    hop1 = attenuate(root, "researcher_agent", {"read", "fetch"}, registry)
    hop2 = attenuate(hop1, "tool_caller_agent", {"read"}, registry)

    # Tamper with an intermediate caveat
    tampered = hop2.copy()
    tampered.caveats[3].caveat_id = "agent=rogue_agent"

    assert verify_signature(tampered, root_key) is False
