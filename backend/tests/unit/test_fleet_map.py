"""Unit tests for FleetMap and build_fleet_map."""

from types import SimpleNamespace

from red_team.recon.fleet_map import FleetMap, build_fleet_map
from registry.agents_registry import AgentRegistry


def test_build_fleet_map_from_mock_tree() -> None:
    """Assert build_fleet_map generates complete FleetMap from mock tree and registry."""
    leaf_uk = SimpleNamespace(
        name="uk_search_agent",
        tools=[SimpleNamespace(name="search_companies")],
        sub_agents=[],
    )
    leaf_usa = SimpleNamespace(
        name="usa_sec_agent",
        tools=[SimpleNamespace(name="get_insider_transactions")],
        sub_agents=[],
    )
    root = SimpleNamespace(
        name="root_agent",
        tools=[],
        sub_agents=[leaf_uk, leaf_usa],
    )

    registry = AgentRegistry()
    registry.register(
        agent_id="root_agent",
        display_name="Root",
        max_scope={"delegate"},
        owner="team",
    )
    registry.register(
        agent_id="uk_search_agent",
        display_name="UK",
        max_scope={"read"},
        owner="team",
    )
    registry.register(
        agent_id="usa_sec_agent",
        display_name="USA",
        max_scope={"read", "query", "export"},
        owner="team",
    )

    tool_actions = {
        "search_companies": "read",
        "get_insider_transactions": "query",
    }

    fleet_map = build_fleet_map(root, registry, tool_actions)
    assert isinstance(fleet_map, FleetMap)
    assert fleet_map.agent_count == 3
    assert fleet_map.tool_count == 2
    assert "root_agent" in fleet_map.agents
    assert "uk_search_agent" in fleet_map.agents
    assert "usa_sec_agent" in fleet_map.agents


def test_weakest_agents_sorted_by_ceiling_breadth() -> None:
    """Assert weakest_agents returns agents sorted descending by scope ceiling size."""
    fleet_map = FleetMap(
        agents={
            "agent_small": {"tools": ["t1"]},
            "agent_large": {"tools": ["t1", "t2", "t3"]},
            "agent_medium": {"tools": ["t1", "t2"]},
        },
        ceilings={
            "agent_small": frozenset({"read"}),
            "agent_large": frozenset({"read", "write", "admin", "delete"}),
            "agent_medium": frozenset({"read", "write"}),
        },
        tool_actions={},
    )

    weakest = fleet_map.weakest_agents()
    assert weakest[0] == "agent_large"
    assert weakest[1] == "agent_medium"
    assert weakest[2] == "agent_small"


def test_boundary_agents_identifies_cross_category() -> None:
    """Assert boundary_agents detects agents coordinating cross-jurisdictional subagents."""
    fleet_map = FleetMap(
        agents={
            "root_coordinator": {
                "sub_agents": ["uk_subagent", "usa_subagent"],
                "tools": [],
            },
            "uk_subagent": {
                "sub_agents": ["uk_leaf_1", "uk_leaf_2"],
                "tools": [],
            },
            "usa_subagent": {
                "sub_agents": [],
                "tools": [],
            },
        },
        ceilings={},
        tool_actions={},
    )

    boundaries = fleet_map.boundary_agents()
    assert "root_coordinator" in boundaries
    # uk_subagent also coordinates 2 subagents
    assert "uk_subagent" in boundaries


def test_fleet_map_to_dict_serializability() -> None:
    """Assert to_dict produces valid dictionary with all required keys."""
    fleet_map = FleetMap(
        agents={"agent_1": {"tools": ["t1"]}},
        ceilings={"agent_1": frozenset({"read"})},
        tool_actions={"t1": "read"},
    )
    d = fleet_map.to_dict()
    assert d["agent_count"] == 1
    assert d["tool_count"] == 1
    assert "agent_1" in d["agents"]
    assert d["ceilings"]["agent_1"] == ["read"]
    assert "weakest_agents" in d
    assert "boundary_agents" in d
