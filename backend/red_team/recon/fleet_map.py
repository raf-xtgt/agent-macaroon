"""FleetMap data structure representing the scanned target fleet architecture."""

from dataclasses import dataclass
from typing import Any

from registry.agents_registry import AgentRegistry

from .probe import probe_agent_tree, probe_registry_ceilings, probe_tool_action_map


@dataclass
class FleetMap:
    """Consolidated reconnaissance map of the target agent fleet."""

    agents: dict[str, dict[str, Any]]
    ceilings: dict[str, frozenset[str]]
    tool_actions: dict[str, str]
    agent_count: int = 0
    tool_count: int = 0

    def __post_init__(self) -> None:
        """Compute counts if not explicitly set."""
        if not self.agent_count:
            self.agent_count = len(self.agents)
        if not self.tool_count:
            unique_tools: set[str] = set()
            for meta in self.agents.values():
                for t in meta.get("tools", []):
                    unique_tools.add(t)
            self.tool_count = len(unique_tools)

    def weakest_agents(self) -> list[str]:
        """Identify agents with the broadest scope ceilings (highest attack surface).

        Returns:
            list[str]: Agent names ordered descending by ceiling breadth.
        """
        scored_agents: list[tuple[str, int]] = []
        for agent_name, meta in self.agents.items():
            ceiling = self.ceilings.get(agent_name)
            if ceiling is not None:
                score = len(ceiling)
            else:
                score = len(meta.get("tools", []))
            scored_agents.append((agent_name, score))

        # Sort descending by score, then alphabetically
        scored_agents.sort(key=lambda x: (-x[1], x[0]))
        return [agent_name for agent_name, _ in scored_agents]

    def boundary_agents(self) -> list[str]:
        """Identify agents that act as boundaries between distinct sub-fleets or tool categories.

        An agent is considered a boundary agent if:
        1. It has subagents spanning multiple naming prefixes/jurisdictions (e.g. 'uk_' vs 'usa_').
        2. Or it is a non-leaf agent coordinating disparate subagents.

        Returns:
            list[str]: Names of identified boundary agents.
        """
        boundaries: list[str] = []
        for agent_name, meta in self.agents.items():
            sub_agents: list[str] = meta.get("sub_agents", [])
            if not sub_agents:
                continue

            # Detect domain/jurisdiction divergence among subagents (e.g. 'uk', 'usa', 'sec', 'ch')
            prefixes = {sub.split("_")[0] for sub in sub_agents if "_" in sub}
            if len(prefixes) > 1:
                boundaries.append(agent_name)
            elif len(sub_agents) >= 2:
                # Coordinator of multiple distinct agents
                boundaries.append(agent_name)

        return boundaries

    def to_dict(self) -> dict[str, Any]:
        """Convert FleetMap to a JSON-serializable dictionary.

        Returns:
            dict[str, Any]: JSON dictionary representation.
        """
        return {
            "agents": self.agents,
            "ceilings": {k: list(v) for k, v in self.ceilings.items()},
            "tool_actions": self.tool_actions,
            "agent_count": self.agent_count,
            "tool_count": self.tool_count,
            "weakest_agents": self.weakest_agents(),
            "boundary_agents": self.boundary_agents(),
        }


def build_fleet_map(
    root_agent: Any,
    registry: AgentRegistry | None = None,
    tool_action_map: dict[str, str] | None = None,
) -> FleetMap:
    """Build a complete FleetMap by probing the agent tree and registry.

    Args:
        root_agent: Root agent instance of the target fleet.
        registry: Optional AgentRegistry instance.
        tool_action_map: Optional tool action verb dictionary.

    Returns:
        FleetMap: Consolidated fleet map.
    """
    agents = probe_agent_tree(root_agent)
    ceilings = probe_registry_ceilings(registry)
    normalized_tool_map = probe_tool_action_map(tool_action_map)

    return FleetMap(
        agents=agents,
        ceilings=ceilings,
        tool_actions=normalized_tool_map,
    )
