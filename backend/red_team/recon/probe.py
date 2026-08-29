"""Fleet reconnaissance probes: inspects ADK agent tree, tools, and registry."""

from typing import Any

from registry.agents_registry import AgentRegistry


def probe_agent_tree(root_agent: Any) -> dict[str, dict[str, Any]]:
    """Recursively probe an ADK agent hierarchy to map agent metadata.

    Args:
        root_agent: Root agent instance of the target fleet.

    Returns:
        dict[str, dict[str, Any]]: Mapping of agent name to agent metadata:
            - name: Agent name
            - depth: Depth in tree (root = 0)
            - tools: List of tool names
            - sub_agents: List of direct subagent names
            - model: Model name/identifier if configured
    """
    if root_agent is None:
        return {}

    tree_map: dict[str, dict[str, Any]] = {}

    def _walk(agent: Any, depth: int) -> None:
        name = getattr(agent, "name", None) or getattr(agent, "__name__", None)
        if not name:
            return

        tool_names: list[str] = []
        for tool in getattr(agent, "tools", None) or []:
            tname = getattr(tool, "name", None) or getattr(tool, "__name__", None)
            if tname:
                tool_names.append(tname)

        sub_agents = getattr(agent, "sub_agents", None) or []
        sub_agent_names: list[str] = []
        for sub in sub_agents:
            if sub is not None:
                sub_name = getattr(sub, "name", None) or getattr(sub, "__name__", None)
                if sub_name:
                    sub_agent_names.append(sub_name)

        model_val = getattr(agent, "model", None)
        model_str: str | None = None
        if model_val is not None:
            model_str = str(model_val)

        tree_map[name] = {
            "name": name,
            "depth": depth,
            "tools": tool_names,
            "sub_agents": sub_agent_names,
            "model": model_str,
        }

        for sub in sub_agents:
            if sub is not None:
                _walk(sub, depth + 1)

    _walk(root_agent, 0)
    return tree_map


def probe_registry_ceilings(
    registry: AgentRegistry | None,
) -> dict[str, frozenset[str]]:
    """Extract scope ceilings from an AgentRegistry instance.

    Args:
        registry: AgentRegistry instance or None.

    Returns:
        dict[str, frozenset[str]]: Mapping of agent ID to ceiling action verbs.
    """
    if registry is None:
        return {}

    ceilings: dict[str, frozenset[str]] = {}
    for agent_id in registry.list_agents():
        ceilings[agent_id] = registry.ceiling(agent_id)
    return ceilings


def probe_tool_action_map(tool_action_map: dict[str, str] | None) -> dict[str, str]:
    """Normalize and validate tool-to-action verb mappings.

    Args:
        tool_action_map: Dictionary mapping tool names to action verbs.

    Returns:
        dict[str, str]: Validated dictionary mapping tool name to action verb.
    """
    if not tool_action_map:
        return {}
    return {str(k): str(v) for k, v in tool_action_map.items()}
