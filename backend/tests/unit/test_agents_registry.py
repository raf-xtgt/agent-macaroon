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


def test_list_agents_returns_registered_ids() -> None:
    """Assert list_agents returns all registered agent IDs."""
    registry = AgentRegistry()
    registry.register(
        agent_id="agent_alpha",
        display_name="Alpha",
        max_scope={"read"},
        owner="team-a",
    )
    registry.register(
        agent_id="agent_beta",
        display_name="Beta",
        max_scope={"write"},
        owner="team-b",
    )
    agents = registry.list_agents()
    assert set(agents) == {"agent_alpha", "agent_beta"}


def test_list_agents_empty_registry() -> None:
    """Assert list_agents returns an empty list for an empty registry."""
    registry = AgentRegistry()
    assert registry.list_agents() == []


class _FakeAgent:
    """Minimal stub matching the attrs derive_from_agent_tree reads."""

    def __init__(self, name, tools=None, sub_agents=None):
        self.name = name
        self.tools = tools or []
        self.sub_agents = sub_agents or []


class _FakeTool:
    def __init__(self, name):
        self.name = name


def test_derive_propagates_descendant_verbs_to_parent() -> None:
    """Intermediate agents with no tools inherit descendants' verbs."""
    leaf_a = _FakeAgent("leaf_a", tools=[_FakeTool("search_companies")])
    leaf_b = _FakeAgent("leaf_b", tools=[_FakeTool("get_company_profile")])
    mid = _FakeAgent("mid", sub_agents=[leaf_a, leaf_b])
    root = _FakeAgent("root", sub_agents=[mid])

    tool_map = {
        "search_companies": "search",
        "get_company_profile": "retrieve",
    }

    config = AgentRegistry.derive_from_agent_tree(root, tool_map)

    assert config["leaf_a"] == {"search"}
    assert config["leaf_b"] == {"retrieve"}
    assert config["mid"] == {"delegate", "search", "retrieve"}
    assert config["root"] == {"delegate", "search", "retrieve"}


def test_derive_leaf_does_not_get_delegate() -> None:
    """A leaf agent with no sub_agents must not receive 'delegate'."""
    leaf = _FakeAgent("leaf", tools=[_FakeTool("get_current_date")])
    root = _FakeAgent("root", sub_agents=[leaf])

    config = AgentRegistry.derive_from_agent_tree(root, {"get_current_date": "read"})

    assert "delegate" not in config["leaf"]
    assert config["leaf"] == {"read"}
    assert config["root"] == {"delegate", "read"}
