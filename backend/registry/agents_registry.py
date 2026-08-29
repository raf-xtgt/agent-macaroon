"""Scope-ceiling lookups and agent registration (in-memory backend for MVP)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentRecord:
    """Represents a registered agent and its maximum allowable scope ceiling.

    Attributes:
        display_name: Human-readable name of the agent.
        max_scope: The maximum-ever permissible set of action verbs for this agent.
        owner: Service or human owner responsible for the agent.
        status: Lifecycle status, either 'active' or 'retired'.
        created_at: Timestamp when the agent was registered.
    """

    display_name: str
    max_scope: frozenset[str]
    owner: str
    status: str
    created_at: datetime


class AgentRegistry:
    """In-memory agent registry tracking scope ceilings and agent statuses.

    Note: This is an in-memory implementation for MVP development and fast unit testing.
    In production milestones, this will be backed by Google Cloud Firestore with the exact
    same public interface (register, ceiling, retire).
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory agent registry."""
        self._records: dict[str, AgentRecord] = {}

    def register(
        self,
        agent_id: str,
        display_name: str,
        max_scope: set[str],
        owner: str,
    ) -> None:
        """Register a new agent or update an existing agent's ceiling.

        Args:
            agent_id: Unique identifier for the agent.
            display_name: Human-readable display name.
            max_scope: Maximum allowable action verbs for this agent.
            owner: Responsible team or service owner.
        """
        self._records[agent_id] = AgentRecord(
            display_name=display_name,
            max_scope=frozenset(max_scope),
            owner=owner,
            status="active",
            created_at=datetime.now(timezone.utc),
        )

    def list_agents(self) -> list[str]:
        """Return a list of all registered agent IDs.

        Returns:
            list[str]: List of agent IDs currently in the registry.
        """
        return list(self._records.keys())

    def ceiling(self, agent_id: str) -> frozenset[str]:
        """Look up the scope ceiling for an agent.

        Fails closed: returns an empty frozenset for unknown or retired agents,
        never raising an exception.

        Args:
            agent_id: Unique identifier for the agent.

        Returns:
            frozenset[str]: Allowed action verbs if agent is active, else frozenset().
        """
        record = self._records.get(agent_id)
        if record is None or record.status != "active":
            return frozenset()
        return record.max_scope

    def retire(self, agent_id: str) -> None:
        """Retire an agent, causing all subsequent ceiling checks to return empty scope.

        Args:
            agent_id: Unique identifier for the agent to retire.
        """
        record = self._records.get(agent_id)
        if record is not None:
            self._records[agent_id] = AgentRecord(
                display_name=record.display_name,
                max_scope=record.max_scope,
                owner=record.owner,
                status="retired",
                created_at=record.created_at,
            )

    def register_bulk(
        self,
        agents_config: dict[str, set[str]],
        owner: str = "auto-derived",
    ) -> None:
        """Register multiple agents at once from a name-to-scope mapping."""
        for agent_id, scope in agents_config.items():
            self.register(
                agent_id=agent_id,
                display_name=agent_id,
                max_scope=scope,
                owner=owner,
            )

    def tighten_ceiling(self, agent_id: str, remove_verbs: set[str]) -> None:
        """Remove action verbs from an active agent's ceiling (immunization)."""
        record = self._records.get(agent_id)
        if record is None or record.status != "active":
            return
        new_scope = record.max_scope - frozenset(remove_verbs)
        self._records[agent_id] = AgentRecord(
            display_name=record.display_name,
            max_scope=new_scope,
            owner=record.owner,
            status=record.status,
            created_at=record.created_at,
        )

    @staticmethod
    def derive_from_agent_tree(
        root_agent: Any,
        tool_action_map: dict[str, str],
    ) -> dict[str, set[str]]:
        """Walk an ADK agent hierarchy and derive scope ceilings from tools.

        Returns a dict mapping agent_id to the set of action verbs it needs,
        derived from its tools and whether it has sub-agents (adds "delegate").
        """
        config: dict[str, set[str]] = {}

        def _walk(agent: Any) -> None:
            name = getattr(agent, "name", None)
            if name is None:
                return

            verbs: set[str] = set()

            tools = getattr(agent, "tools", None) or []
            for tool in tools:
                tool_name = getattr(tool, "name", None) or getattr(
                    tool, "__name__", None
                )
                if tool_name:
                    action = tool_action_map.get(tool_name)
                    if action:
                        verbs.add(action)

            sub_agents = getattr(agent, "sub_agents", None) or []
            if sub_agents:
                verbs.add("delegate")

            config[name] = verbs

            for sub in sub_agents:
                _walk(sub)

        _walk(root_agent)
        return config
