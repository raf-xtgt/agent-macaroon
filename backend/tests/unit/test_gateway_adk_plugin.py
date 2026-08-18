"""Unit tests for the ADK GatewayPlugin adapter."""

from types import SimpleNamespace
from typing import Any

import pytest

from gateway.adapters.adk_plugin import GatewayPlugin
from macaroon.attenuate import attenuate
from macaroon.issue import issue_root_macaroon
from registry.agents_registry import AgentRegistry


@pytest.fixture
def test_setup() -> dict[str, Any]:
    """Fixture providing initialized root key, registry, and registered agent."""
    root_key = b"test-secret-root-key"
    registry = AgentRegistry()
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )
    plugin = GatewayPlugin(root_key=root_key, registry=registry)
    return {
        "root_key": root_key,
        "registry": registry,
        "plugin": plugin,
    }


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
