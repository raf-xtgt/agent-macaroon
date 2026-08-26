"""Unit tests for blast radius calculation (risk scoring & tree traversal)."""

from types import SimpleNamespace
from typing import Any

from blast.radius import (
    BlastRadiusResult,
    compute_blast_radius,
)


def _make_mock_tree() -> Any:
    """Create a mock 3-agent tree: root -> intermediate -> leaf."""
    # Leaf agent with high sensitivity tools
    leaf_agent = SimpleNamespace(
        name="leaf_agent",
        tools=[
            SimpleNamespace(name="get_insider_transactions"),  # HIGH (10)
            SimpleNamespace(name="get_company_officers"),  # HIGH (10)
        ],
        sub_agents=[],
    )

    # Intermediate agent with medium sensitivity tools
    mid_agent = SimpleNamespace(
        name="mid_agent",
        tools=[
            SimpleNamespace(name="get_company_charges"),  # MEDIUM (5)
            SimpleNamespace(name="search_companies"),  # LOW (2)
        ],
        sub_agents=[leaf_agent],
    )

    # Root agent with low / none sensitivity tools
    root_agent = SimpleNamespace(
        name="root_agent",
        tools=[
            SimpleNamespace(name="google_search"),  # LOW (2)
            SimpleNamespace(name="get_current_date"),  # NONE (0)
        ],
        sub_agents=[mid_agent],
    )

    return root_agent


def test_blast_radius_root_injection_reaches_all_agents() -> None:
    """Assert injection at root agent traverses all reachable children and tools."""
    tree = _make_mock_tree()
    tool_action_map = {
        "google_search": "search",
        "get_current_date": "read",
        "get_company_charges": "retrieve",
        "search_companies": "search",
        "get_insider_transactions": "retrieve",
        "get_company_officers": "retrieve",
    }

    result = compute_blast_radius(
        root_agent=tree,
        injection_agent="root_agent",
        tool_action_map=tool_action_map,
    )

    assert isinstance(result, BlastRadiusResult)
    assert result.reachable_agent_count == 3
    assert result.reachable_agents == ["root_agent", "mid_agent", "leaf_agent"]

    expected_tools = [
        "google_search",
        "get_current_date",
        "get_company_charges",
        "search_companies",
        "get_insider_transactions",
        "get_company_officers",
    ]
    assert result.exposed_tool_count == 6
    assert result.exposed_tools == expected_tools

    # Score: LOW(2) + NONE(0) + MEDIUM(5) + LOW(2) + HIGH(10) + HIGH(10) = 29
    assert result.score == 29
    assert result.sensitivity_breakdown == {
        "HIGH": 2,
        "MEDIUM": 1,
        "LOW": 2,
        "NONE": 1,
    }
    assert result.max_sensitivity == "HIGH"


def test_blast_radius_leaf_injection_reaches_only_leaf() -> None:
    """Assert injection at leaf agent only reaches leaf agent and its own tools."""
    tree = _make_mock_tree()
    tool_action_map = {
        "get_insider_transactions": "retrieve",
        "get_company_officers": "retrieve",
    }

    result = compute_blast_radius(
        root_agent=tree,
        injection_agent="leaf_agent",
        tool_action_map=tool_action_map,
    )

    assert result.reachable_agent_count == 1
    assert result.reachable_agents == ["leaf_agent"]
    assert result.exposed_tool_count == 2
    assert result.exposed_tools == [
        "get_insider_transactions",
        "get_company_officers",
    ]
    # Score: HIGH(10) + HIGH(10) = 20
    assert result.score == 20
    assert result.sensitivity_breakdown == {
        "HIGH": 2,
        "MEDIUM": 0,
        "LOW": 0,
        "NONE": 0,
    }
    assert result.max_sensitivity == "HIGH"


def test_blast_radius_mid_agent_injection() -> None:
    """Assert injection at mid agent reaches mid and leaf agents only."""
    tree = _make_mock_tree()
    result = compute_blast_radius(
        root_agent=tree,
        injection_agent="mid_agent",
        tool_action_map={},
    )

    assert result.reachable_agent_count == 2
    assert result.reachable_agents == ["mid_agent", "leaf_agent"]
    assert result.exposed_tool_count == 4
    # Score: MEDIUM(5) + LOW(2) + HIGH(10) + HIGH(10) = 27
    assert result.score == 27
    assert result.sensitivity_breakdown == {
        "HIGH": 2,
        "MEDIUM": 1,
        "LOW": 1,
        "NONE": 0,
    }
    assert result.max_sensitivity == "HIGH"


def test_blast_radius_unknown_tools_default_to_none() -> None:
    """Assert tools not present in SENSITIVITY map default to NONE sensitivity (weight 0)."""
    custom_leaf = SimpleNamespace(
        name="custom_leaf",
        tools=[
            SimpleNamespace(name="unregistered_custom_tool"),
            SimpleNamespace(name="another_custom_tool"),
        ],
        sub_agents=[],
    )

    result = compute_blast_radius(
        root_agent=custom_leaf,
        injection_agent="custom_leaf",
        tool_action_map={},
    )

    assert result.reachable_agent_count == 1
    assert result.exposed_tool_count == 2
    assert result.score == 0
    assert result.sensitivity_breakdown == {
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "NONE": 2,
    }
    assert result.max_sensitivity == "NONE"


def test_blast_radius_unknown_injection_agent_fallback() -> None:
    """Assert unknown injection_agent falls back to root agent safely."""
    tree = _make_mock_tree()
    result = compute_blast_radius(
        root_agent=tree,
        injection_agent="non_existent_agent",
        tool_action_map={},
    )

    # Falls back to root_agent traversal
    assert result.reachable_agent_count == 3
    assert result.score == 29
