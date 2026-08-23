"""Closed-loop multi-hop delegation and tool enforcement test (Part C)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pymacaroons import Macaroon

from gateway.adapters.adk_plugin import GatewayPlugin
from macaroon.attenuate import current_scope
from registry.agents_registry import AgentRegistry


class _FakeRecordsQuery:
    def __init__(self, agent_id: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.agent_id = agent_id
        self.store = store

    def where(self, *args: Any, **kwargs: Any) -> "_FakeRecordsQuery":
        return self

    def limit(self, count: int) -> "_FakeRecordsQuery":
        return self

    def stream(self) -> Any:
        for r in self.store.get(self.agent_id, []):
            doc = MagicMock()
            doc.to_dict.return_value = r
            yield doc


class _FakeAgentDoc:
    def __init__(self, agent_id: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.agent_id = agent_id
        self.store = store

    def collection(self, name: str) -> _FakeRecordsQuery:
        if name == "records":
            return _FakeRecordsQuery(self.agent_id, self.store)
        raise ValueError(f"Unknown subcollection: {name}")


class _FakeMemoryCollection:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self.store = store

    def document(self, agent_id: str) -> _FakeAgentDoc:
        return _FakeAgentDoc(agent_id, self.store)


class _FakeFirestoreDB:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def collection(self, name: str) -> Any:
        if name == "agent_memory":
            return _FakeMemoryCollection(self.store)
        raise ValueError(f"Unknown collection: {name}")


@pytest.mark.asyncio
async def test_full_delegation_and_enforcement_loop() -> None:
    """Prove the complete multi-hop capability delegation and tool verification lifecycle.

    Lifecycle:
    1. Human message triggers on_user_message_callback (F1) -> mints root macaroon.
    2. orchestrator_agent receives token via before_agent_callback (F2) -> bound to orchestrator.
    3. researcher_agent receives delegation via before_agent_callback (F2) -> scope narrows to researcher ceiling.
    4. tool_caller_agent receives delegation via before_agent_callback (F2) -> scope narrows to tool_caller ceiling.
    5. tool_caller_agent executes in-scope tool ('read_record') -> permitted (F4).
    6. tool_caller_agent executes out-of-scope tool ('delete_record') -> denied fail-closed (F4).
    """
    root_key = b"enterprise-closed-loop-root-key"
    # Initial scope includes 'delegate' so orchestrator and researcher can execute hand-offs
    initial_scope = {"read", "delete", "fetch", "delegate"}

    # Setup Agent Registry with three distinct ceilings
    registry = AgentRegistry()
    registry.register(
        agent_id="orchestrator_agent",
        display_name="Orchestrator Root Agent",
        max_scope={"read", "delete", "fetch", "delegate"},
        owner="core-orchestration",
    )
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher Specialist",
        # Researcher has sub_agents, so max_scope includes 'delegate' while excluding 'delete'
        max_scope={"read", "fetch", "delegate"},
        owner="research-team",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller Leaf Agent",
        # Tool caller is a leaf agent with no sub_agents: only 'read' permitted in this scenario
        max_scope={"read"},
        owner="execution-team",
    )

    plugin = GatewayPlugin(
        root_key=root_key,
        registry=registry,
        initial_scope=initial_scope,
    )

    fake_db = _FakeFirestoreDB()
    with patch("memory.behavior._get_firestore_client", return_value=fake_db):
        # 0. Shared mutable session state across the entire chain
        shared_session_state: dict[str, Any] = {}

        # 1. Step 1: User message arrives (F1)
        session = SimpleNamespace(state=shared_session_state)
        invocation_context = SimpleNamespace(
            user_id="alice@enterprise.com",
            invocation_id="chain-uuid-prod-101",
            session=session,
        )
        user_msg = SimpleNamespace(
            parts=[SimpleNamespace(text="Investigate incident #101")]
        )

        msg_res = await plugin.on_user_message_callback(
            invocation_context=invocation_context,  # type: ignore[arg-type]
            user_message=user_msg,  # type: ignore[arg-type]
        )
        assert msg_res is None
        assert "agent_macaroon" in shared_session_state

        # Root token carries the full 4-action initial grant (read, delete, fetch, delegate)
        token_step1 = Macaroon.deserialize(shared_session_state["agent_macaroon"])
        assert current_scope(token_step1) == frozenset(
            {"read", "delete", "fetch", "delegate"}
        )

        # 2. Step 2: Handoff to orchestrator_agent (F2 - Hop 1)
        callback_ctx = SimpleNamespace(state=shared_session_state)
        orch_agent = SimpleNamespace(name="orchestrator_agent")

        orch_res = await plugin.before_agent_callback(
            agent=orch_agent,  # type: ignore[arg-type]
            callback_context=callback_ctx,  # type: ignore[arg-type]
        )
        assert orch_res is None

        # Token bound to orchestrator retains full scope matching orchestrator ceiling
        token_step2 = Macaroon.deserialize(shared_session_state["agent_macaroon"])
        assert current_scope(token_step2) == frozenset(
            {"read", "delete", "fetch", "delegate"}
        )

        # 3. Step 3: Delegation from orchestrator to researcher_agent (F2 - Hop 2)
        researcher_agent = SimpleNamespace(name="researcher_agent")
        research_res = await plugin.before_agent_callback(
            agent=researcher_agent,  # type: ignore[arg-type]
            callback_context=callback_ctx,  # type: ignore[arg-type]
        )
        assert research_res is None

        token_step3 = Macaroon.deserialize(shared_session_state["agent_macaroon"])
        # Narrowed from {"read", "delete", "fetch", "delegate"} to {"read", "fetch", "delegate"} ('delete' stripped)
        assert current_scope(token_step3) == frozenset({"read", "fetch", "delegate"})
        assert current_scope(token_step3).issubset(current_scope(token_step2))

        # 4. Step 4: Delegation from researcher to tool_caller_agent (F2 - Hop 3)
        tool_caller_agent = SimpleNamespace(name="tool_caller_agent")
        tool_caller_res = await plugin.before_agent_callback(
            agent=tool_caller_agent,  # type: ignore[arg-type]
            callback_context=callback_ctx,  # type: ignore[arg-type]
        )
        assert tool_caller_res is None

        token_step4 = Macaroon.deserialize(shared_session_state["agent_macaroon"])
        # Narrowed from {"read", "fetch", "delegate"} to {"read"} ('fetch' and 'delegate' stripped by leaf ceiling)
        assert current_scope(token_step4) == frozenset({"read"})
        assert current_scope(token_step4).issubset(current_scope(token_step3))

    # 5. Step 5: tool_caller_agent invokes in-scope tool 'read_record' (F4 - Tool Check 1)
    tool_read = SimpleNamespace(name="read_record")
    tool_ctx_read = SimpleNamespace(
        agent_name="tool_caller_agent",
        state=shared_session_state,
    )
    read_decision = await plugin.before_tool_callback(
        tool=tool_read,  # type: ignore[arg-type]
        tool_args={"id": "doc_99"},
        tool_context=tool_ctx_read,  # type: ignore[arg-type]
    )
    # Must be allowed
    assert read_decision is None

    # 6. Step 6: tool_caller_agent attempts out-of-scope tool 'delete_record' (F4 - Tool Check 2)
    tool_delete = SimpleNamespace(name="delete_record")
    tool_ctx_delete = SimpleNamespace(
        agent_name="tool_caller_agent",
        state=shared_session_state,
    )
    delete_decision = await plugin.before_tool_callback(
        tool=tool_delete,  # type: ignore[arg-type]
        tool_args={"id": "doc_99"},
        tool_context=tool_ctx_delete,  # type: ignore[arg-type]
    )
    # Must be denied
    assert delete_decision is not None
    assert isinstance(delete_decision, dict)
    assert delete_decision.get("error") == "denied_by_gateway"
    assert "scope caveat violated" in delete_decision.get("reason", "")
    assert "requested=delete" in delete_decision.get("reason", "")
    assert "allowed=read" in delete_decision.get("reason", "")
