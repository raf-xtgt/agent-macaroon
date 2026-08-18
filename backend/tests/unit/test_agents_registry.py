"""Unit tests for AgentRegistry (F3 scope ceiling enforcement)."""

from registry.agents_registry import AgentRegistry


def test_register_and_ceiling_roundtrip() -> None:
    """Assert registered agent returns the expected scope ceiling."""
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller Agent",
        max_scope={"read", "write"},
        owner="security-team",
    )

    ceiling = registry.ceiling("tool_caller_agent")
    assert ceiling == frozenset({"read", "write"})


def test_unknown_agent_ceiling_fails_closed() -> None:
    """Assert querying an unregistered agent returns an empty frozenset (fail closed)."""
    registry = AgentRegistry()
    ceiling = registry.ceiling("unregistered_agent")
    assert ceiling == frozenset()


def test_retired_agent_ceiling_fails_closed() -> None:
    """Assert retiring an agent revokes all ceilings and returns an empty frozenset."""
    registry = AgentRegistry()
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher Agent",
        max_scope={"read", "fetch"},
        owner="core-team",
    )
    assert registry.ceiling("researcher_agent") == frozenset({"read", "fetch"})

    registry.retire("researcher_agent")
    assert registry.ceiling("researcher_agent") == frozenset()


def test_retire_nonexistent_agent_is_safe() -> None:
    """Assert retiring a non-existent agent does not raise an exception."""
    registry = AgentRegistry()
    registry.retire("nonexistent_agent")
    assert registry.ceiling("nonexistent_agent") == frozenset()


def test_prd_f3_ceiling_exclusion() -> None:
    """PRD F3 acceptance: registering tool caller with read ceiling excludes write and delete."""
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Read Only Worker",
        max_scope={"read"},
        owner="security-team",
    )

    ceiling = registry.ceiling("tool_caller_agent")
    assert "read" in ceiling
    assert "write" not in ceiling
    assert "delete" not in ceiling
