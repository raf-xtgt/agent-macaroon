"""Unit tests for the ADK GatewayPlugin adapter (F1, F2, F4)."""

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types
from pymacaroons import Macaroon

from gateway.adapters.adk_plugin import GatewayPlugin
from macaroon.attenuate import attenuate, current_scope
from macaroon.issue import issue_root_macaroon, parse_identifier
from registry.agents_registry import AgentRegistry


@pytest.fixture
def test_setup() -> dict[str, Any]:
    """Fixture providing initialized root key, registry, initial scope, and plugin."""
    root_key = b"test-secret-root-key"
    initial_scope = {"read", "delete", "fetch"}
    registry = AgentRegistry()
    registry.register(
        agent_id="orchestrator_agent",
        display_name="Orchestrator Root",
        max_scope={"read", "delete", "fetch"},
        owner="sec-team",
    )
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher Specialist",
        max_scope={"read", "fetch"},
        owner="sec-team",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller Leaf",
        max_scope={"read", "delete"},
        owner="sec-team",
    )
    plugin = GatewayPlugin(
        root_key=root_key,
        registry=registry,
        initial_scope=initial_scope,
    )
    return {
        "root_key": root_key,
        "initial_scope": initial_scope,
        "registry": registry,
        "plugin": plugin,
    }


# ============================================================================
# F1: on_user_message_callback Tests
# ============================================================================


@pytest.mark.asyncio
async def test_on_user_message_issues_root_macaroon(
    test_setup: dict[str, Any],
) -> None:
    """Assert on_user_message_callback mints root macaroon into session state with provenance."""
    plugin = test_setup["plugin"]
    state_dict: dict[str, Any] = {}
    session = SimpleNamespace(state=state_dict)
    invocation_context = SimpleNamespace(
        user_id="user_charlie",
        invocation_id="inv-chain-777",
        session=session,
    )
    user_message = SimpleNamespace(
        parts=[SimpleNamespace(text="Retrieve confidential financial logs")]
    )

    res = await plugin.on_user_message_callback(
        invocation_context=invocation_context,  # type: ignore[arg-type]
        user_message=user_message,  # type: ignore[arg-type]
    )

    assert res is None
    assert "agent_macaroon" in state_dict

    macaroon = Macaroon.deserialize(state_dict["agent_macaroon"])
    provenance = parse_identifier(macaroon)

    assert provenance["human_subject_id"] == "user_charlie"
    assert provenance["purpose"] == "Retrieve confidential financial logs"
    assert provenance["chain_id"] == "inv-chain-777"
    assert current_scope(macaroon) == frozenset({"read", "delete", "fetch"})


@pytest.mark.asyncio
async def test_on_user_message_fallback_purpose_on_empty_content(
    test_setup: dict[str, Any],
) -> None:
    """Assert empty or non-text message content falls back to placeholder purpose without error."""
    plugin = test_setup["plugin"]
    state_dict: dict[str, Any] = {}
    session = SimpleNamespace(state=state_dict)
    invocation_context = SimpleNamespace(
        user_id="user_anonymous",
        invocation_id="inv-chain-888",
        session=session,
    )
    user_message = SimpleNamespace(parts=[])

    res = await plugin.on_user_message_callback(
        invocation_context=invocation_context,  # type: ignore[arg-type]
        user_message=user_message,  # type: ignore[arg-type]
    )

    assert res is None
    assert "agent_macaroon" in state_dict

    macaroon = Macaroon.deserialize(state_dict["agent_macaroon"])
    provenance = parse_identifier(macaroon)
    assert provenance["purpose"] == "(no text content)"


@pytest.mark.asyncio
async def test_on_user_message_initial_scope_match(
    test_setup: dict[str, Any],
) -> None:
    """Assert issued macaroon scope exactly matches plugin configured initial_scope."""
    plugin = test_setup["plugin"]
    state_dict: dict[str, Any] = {}
    session = SimpleNamespace(state=state_dict)
    invocation_context = SimpleNamespace(
        user_id="user_admin",
        invocation_id="inv-123",
        session=session,
    )
    user_message = SimpleNamespace(parts=[SimpleNamespace(text="Do task")])

    await plugin.on_user_message_callback(
        invocation_context=invocation_context,  # type: ignore[arg-type]
        user_message=user_message,  # type: ignore[arg-type]
    )

    macaroon = Macaroon.deserialize(state_dict["agent_macaroon"])
    assert current_scope(macaroon) == frozenset(test_setup["initial_scope"])


# ============================================================================
# F2: before_agent_callback Tests
# ============================================================================


@pytest.mark.asyncio
async def test_before_agent_entry_agent_attenuation(
    test_setup: dict[str, Any],
) -> None:
    """Assert before_agent_callback attenuates root macaroon for the entry agent."""
    root_key = test_setup["root_key"]
    plugin = test_setup["plugin"]

    root = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Entry task",
        initial_scope={"read", "delete", "fetch"},
        root_key=root_key,
    )
    state = {"agent_macaroon": root.serialize()}
    callback_context = SimpleNamespace(state=state)
    agent = SimpleNamespace(name="orchestrator_agent")

    res = await plugin.before_agent_callback(
        agent=agent,  # type: ignore[arg-type]
        callback_context=callback_context,  # type: ignore[arg-type]
    )

    assert res is None
    attenuated = Macaroon.deserialize(state["agent_macaroon"])
    # Last caveat must be agent=orchestrator_agent
    caveats = [
        c.caveat_id if isinstance(c.caveat_id, str) else c.caveat_id.decode("utf-8")
        for c in attenuated.first_party_caveats()
    ]
    assert any(c == "agent=orchestrator_agent" for c in caveats)
    assert current_scope(attenuated) == frozenset({"read", "delete", "fetch"})


@pytest.mark.asyncio
async def test_before_agent_delegation_hop_narrows_scope(
    test_setup: dict[str, Any],
) -> None:
    """Assert delegation to researcher_agent narrows scope based on researcher's ceiling."""
    root_key = test_setup["root_key"]
    registry = test_setup["registry"]
    plugin = test_setup["plugin"]

    # Start from an orchestrator-bound macaroon
    root = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Task",
        initial_scope={"read", "delete", "fetch"},
        root_key=root_key,
    )
    orch_macaroon = attenuate(
        macaroon=root,
        to_agent_id="orchestrator_agent",
        task_required_scope={"read", "delete", "fetch"},
        registry=registry,
    )

    state = {"agent_macaroon": orch_macaroon.serialize()}
    callback_context = SimpleNamespace(state=state)
    agent = SimpleNamespace(name="researcher_agent")

    res = await plugin.before_agent_callback(
        agent=agent,  # type: ignore[arg-type]
        callback_context=callback_context,  # type: ignore[arg-type]
    )

    assert res is None
    attenuated = Macaroon.deserialize(state["agent_macaroon"])
    # researcher ceiling is {"read", "fetch"}, so "delete" is filtered out
    assert current_scope(attenuated) == frozenset({"read", "fetch"})


@pytest.mark.asyncio
async def test_before_agent_missing_macaroon_denied(
    test_setup: dict[str, Any],
) -> None:
    """Assert before_agent_callback fails closed when no macaroon is present in state."""
    plugin = test_setup["plugin"]
    state: dict[str, Any] = {}
    callback_context = SimpleNamespace(state=state)
    agent = SimpleNamespace(name="orchestrator_agent")

    res = await plugin.before_agent_callback(
        agent=agent,  # type: ignore[arg-type]
        callback_context=callback_context,  # type: ignore[arg-type]
    )

    assert res is not None
    assert isinstance(res, types.Content)
    assert res.role == "model"
    assert any("No delegation macaroon found" in p.text for p in res.parts or [])


@pytest.mark.asyncio
async def test_before_agent_tampered_signature_denied(
    test_setup: dict[str, Any],
) -> None:
    """Assert tampered macaroon is rejected at delegation time before attenuation."""
    root_key = test_setup["root_key"]
    plugin = test_setup["plugin"]

    root = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Task",
        initial_scope={"read"},
        root_key=root_key,
    )
    tampered = root.copy()
    tampered.caveats[0].caveat_id = "scope=read,admin,root"

    state = {"agent_macaroon": tampered.serialize()}
    callback_context = SimpleNamespace(state=state)
    agent = SimpleNamespace(name="orchestrator_agent")

    res = await plugin.before_agent_callback(
        agent=agent,  # type: ignore[arg-type]
        callback_context=callback_context,  # type: ignore[arg-type]
    )

    assert res is not None
    assert isinstance(res, types.Content)
    assert any("Invalid or tampered macaroon" in p.text for p in res.parts or [])


@pytest.mark.asyncio
async def test_before_agent_depth_exhaustion_denied(
    test_setup: dict[str, Any],
) -> None:
    """Assert delegation depth exhaustion triggers fail-closed denial Content."""
    root_key = test_setup["root_key"]
    registry = test_setup["registry"]
    plugin = test_setup["plugin"]

    # Issue with max_depth=1
    root = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="One hop only",
        initial_scope={"read"},
        root_key=root_key,
        max_depth=1,
    )
    # Hop 1 reduces max_depth to 0
    hop1 = attenuate(
        macaroon=root,
        to_agent_id="orchestrator_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    state = {"agent_macaroon": hop1.serialize()}
    callback_context = SimpleNamespace(state=state)
    agent = SimpleNamespace(name="researcher_agent")

    res = await plugin.before_agent_callback(
        agent=agent,  # type: ignore[arg-type]
        callback_context=callback_context,  # type: ignore[arg-type]
    )

    assert res is not None
    assert isinstance(res, types.Content)
    assert any("Delegation depth exceeded" in p.text for p in res.parts or [])


# ============================================================================
# F4: before_tool_callback Tests
# ============================================================================


@pytest.mark.asyncio
async def test_plugin_allow_case(test_setup: dict[str, Any]) -> None:
    """Assert valid serialized macaroon in session state allows known in-scope tool execution."""
    root_key = test_setup["root_key"]
    registry = test_setup["registry"]
    plugin = test_setup["plugin"]

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": delegated.serialize()},
    )

    result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={"record_id": "rec-123"},
        tool_context=tool_context,  # type: ignore[arg-type]
    )

    # Allow case must return None
    assert result is None


@pytest.mark.asyncio
async def test_plugin_deny_no_macaroon(test_setup: dict[str, Any]) -> None:
    """Assert tool execution without a macaroon in state is denied."""
    plugin = test_setup["plugin"]

    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={},
    )

    result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result.get("error") == "denied_by_gateway"
    assert "no macaroon presented" in result.get("reason", "")


@pytest.mark.asyncio
async def test_plugin_deny_malformed_macaroon(test_setup: dict[str, Any]) -> None:
    """Assert malformed macaroon string in state is handled safely and denied."""
    plugin = test_setup["plugin"]

    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": "not-a-valid-serialized-macaroon-string-@@@!!!"},
    )

    result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result.get("error") == "denied_by_gateway"
    assert "no macaroon presented" in result.get("reason", "")


@pytest.mark.asyncio
async def test_plugin_deny_unmapped_tool(test_setup: dict[str, Any]) -> None:
    """Assert unmapped tool name routes through evaluation and is denied."""
    root_key = test_setup["root_key"]
    registry = test_setup["registry"]
    plugin = test_setup["plugin"]

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    tool = SimpleNamespace(name="drop_all_tables")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": delegated.serialize()},
    )

    result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result.get("error") == "denied_by_gateway"
    assert "unknown_tool:drop_all_tables" in result.get("reason", "")


@pytest.mark.asyncio
async def test_plugin_uses_actual_agent_name_from_context(
    test_setup: dict[str, Any],
) -> None:
    """Assert plugin extracts agent identity from tool_context.agent_name and enforces caveats."""
    root_key = test_setup["root_key"]
    registry = test_setup["registry"]
    plugin = test_setup["plugin"]

    # Register an attacker agent in registry with read ceiling
    registry.register(
        agent_id="attacker_agent",
        display_name="Attacker Agent",
        max_scope={"read"},
        owner="sec-team",
    )

    # Macaroon is delegated specifically to tool_caller_agent
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    # Attacker tries to execute read_record using tool_caller_agent's macaroon
    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="attacker_agent",  # ADK context identifies this as attacker_agent
        state={"agent_macaroon": delegated.serialize()},
    )

    result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result.get("error") == "denied_by_gateway"
    assert "agent caveat violated" in result.get("reason", "")
    assert "presenting=attacker_agent" in result.get("reason", "")
    assert "expected=tool_caller_agent" in result.get("reason", "")
