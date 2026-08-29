"""Unit tests for fleet reconnaissance probe functions."""

from types import SimpleNamespace

from red_team.recon.probe import (
    probe_agent_tree,
    probe_registry_ceilings,
    probe_tool_action_map,
)
from registry.agents_registry import AgentRegistry


def test_probe_agent_tree_discovers_all_agents() -> None:
    """Assert probe_agent_tree recursively traverses an agent tree."""
    leaf1 = SimpleNamespace(
        name="uk_search_agent",
        tools=[SimpleNamespace(name="search_companies")],
        sub_agents=[],
        model="gemini-2.5-flash",
    )
    leaf2 = SimpleNamespace(
        name="usa_sec_agent",
        tools=[SimpleNamespace(name="get_insider_transactions")],
        sub_agents=[],
        model="gemini-2.5-flash",
    )
    root = SimpleNamespace(
        name="root_kyc_agent",
        tools=[],
        sub_agents=[leaf1, leaf2],
        model="gemini-3.5-flash",
    )

    tree = probe_agent_tree(root)
    assert len(tree) == 3
    assert "root_kyc_agent" in tree
    assert "uk_search_agent" in tree
    assert "usa_sec_agent" in tree

    assert tree["root_kyc_agent"]["depth"] == 0
    assert tree["root_kyc_agent"]["sub_agents"] == ["uk_search_agent", "usa_sec_agent"]
    assert tree["uk_search_agent"]["depth"] == 1
    assert tree["uk_search_agent"]["tools"] == ["search_companies"]


def test_probe_registry_ceilings_returns_all_ceilings() -> None:
    """Assert probe_registry_ceilings extracts all registered ceilings."""
    registry = AgentRegistry()
    registry.register(
        agent_id="agent_1",
        display_name="Agent 1",
        max_scope={"read"},
        owner="sec-team",
    )
    registry.register(
        agent_id="agent_2",
        display_name="Agent 2",
        max_scope={"read", "write", "delete"},
        owner="sec-team",
    )

    ceilings = probe_registry_ceilings(registry)
    assert len(ceilings) == 2
    assert ceilings["agent_1"] == frozenset({"read"})
    assert ceilings["agent_2"] == frozenset({"read", "write", "delete"})


def test_probe_agent_tree_handles_no_tools_or_subagents() -> None:
    """Assert probe_agent_tree safely handles leaf agents with empty attributes."""
    leaf = SimpleNamespace(name="bare_agent", tools=None, sub_agents=None)
    tree = probe_agent_tree(leaf)
    assert "bare_agent" in tree
    assert tree["bare_agent"]["tools"] == []
    assert tree["bare_agent"]["sub_agents"] == []


def test_probe_tool_action_map_normalizes_dict() -> None:
    """Assert probe_tool_action_map safely returns string-normalized dictionary."""
    assert probe_tool_action_map(None) == {}
    assert probe_tool_action_map({"tool_a": "read"}) == {"tool_a": "read"}
