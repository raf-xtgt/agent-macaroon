"""Blast radius calculation for blocked attacks."""

from collections import deque
from dataclasses import dataclass
from typing import Any

SENSITIVITY: dict[str, str] = {
    "get_insider_transactions": "HIGH",
    "get_company_officers": "HIGH",
    "get_corporate_officer_disqualifications": "HIGH",
    "get_natural_officer_disqualifications": "HIGH",
    "get_office_appointments": "HIGH",
    "get_company_charges": "MEDIUM",
    "get_company_insolvency": "MEDIUM",
    "get_company_profile": "MEDIUM",
    "get_company_filing_history": "MEDIUM",
    "get_company_filing_detail": "MEDIUM",
    "get_company_exemptions": "MEDIUM",
    "get_company_establishments": "LOW",
    "get_company_registers": "LOW",
    "search_companies": "LOW",
    "full_text_search": "LOW",
    "get_recent_filings": "LOW",
    "extract_filing_section": "LOW",
    "google_search": "LOW",
    "get_current_date": "NONE",
}

SENSITIVITY_WEIGHTS: dict[str, int] = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
    "NONE": 0,
}

_SENSITIVITY_RANK: dict[str, int] = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "NONE": 0,
}


@dataclass(frozen=True)
class BlastRadiusResult:
    """Result of blast radius computation."""

    score: int
    reachable_agents: list[str]
    reachable_agent_count: int
    exposed_tools: list[str]
    exposed_tool_count: int
    sensitivity_breakdown: dict[str, int]  # {"HIGH": 3, "MEDIUM": 5, ...}
    max_sensitivity: str  # highest sensitivity level among reachable tools


def _find_agent_node(agent: Any, target_name: str) -> Any | None:
    """Recursively search for an agent node with matching name in an ADK agent tree."""
    if agent is None:
        return None
    name = getattr(agent, "name", None) or getattr(agent, "__name__", None)
    if name == target_name:
        return agent
    for sub in getattr(agent, "sub_agents", None) or []:
        found = _find_agent_node(sub, target_name)
        if found is not None:
            return found
    return None


def compute_blast_radius(
    root_agent: Any,
    injection_agent: str,
    tool_action_map: dict[str, str],
) -> BlastRadiusResult:
    """Compute what damage a blocked attack would have caused from an injection point.

    Performs a BFS traversal of the agent tree starting at the injection agent downward,
    enumerates all reachable downstream agents and their exposed tools, and computes a
    sensitivity-weighted blast radius risk score.

    Args:
        root_agent: The root agent of the fleet hierarchy.
        injection_agent: The name of the agent where the attack entered or targeted.
        tool_action_map: Mapping of tool names to action verbs.

    Returns:
        BlastRadiusResult: Metrics containing reachable agents, exposed tools,
            sensitivity breakdown, and weighted risk score.
    """
    start_node = _find_agent_node(root_agent, injection_agent)

    if start_node is None:
        # Fallback: if injection_agent is not found in tree, start from root_agent if available
        start_node = root_agent

    reachable_agents: list[str] = []
    exposed_tools_set: set[str] = set()
    exposed_tools_ordered: list[str] = []

    if start_node is not None:
        queue: deque[Any] = deque([start_node])
        visited_agents: set[str] = set()

        while queue:
            curr = queue.popleft()
            curr_name = (
                getattr(curr, "name", None)
                or getattr(curr, "__name__", None)
                or "unknown_agent"
            )

            if curr_name in visited_agents:
                continue
            visited_agents.add(curr_name)
            reachable_agents.append(curr_name)

            tools = getattr(curr, "tools", None) or []
            for tool in tools:
                tool_name = (
                    getattr(tool, "name", None) or getattr(tool, "__name__", None) or ""
                )
                if tool_name and tool_name not in exposed_tools_set:
                    exposed_tools_set.add(tool_name)
                    exposed_tools_ordered.append(tool_name)

            for sub in getattr(curr, "sub_agents", None) or []:
                if sub is not None:
                    queue.append(sub)

    breakdown: dict[str, int] = {
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "NONE": 0,
    }

    max_rank = 0
    max_sensitivity = "NONE"
    total_score = 0

    for tool_name in exposed_tools_ordered:
        sens = SENSITIVITY.get(tool_name, "NONE")
        breakdown[sens] = breakdown.get(sens, 0) + 1
        total_score += SENSITIVITY_WEIGHTS.get(sens, 0)

        rank = _SENSITIVITY_RANK.get(sens, 0)
        if rank > max_rank:
            max_rank = rank
            max_sensitivity = sens

    return BlastRadiusResult(
        score=total_score,
        reachable_agents=reachable_agents,
        reachable_agent_count=len(reachable_agents),
        exposed_tools=exposed_tools_ordered,
        exposed_tool_count=len(exposed_tools_ordered),
        sensitivity_breakdown=breakdown,
        max_sensitivity=max_sensitivity,
    )
