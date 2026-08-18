"""Scope-ceiling lookups and agent registration (in-memory backend for MVP)."""

from dataclasses import dataclass
from datetime import datetime, timezone


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
