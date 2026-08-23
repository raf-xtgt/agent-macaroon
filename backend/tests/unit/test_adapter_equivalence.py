"""Equivalence tests demonstrating identical decisions across ADK and non-ADK adapters.

Feeds the same macaroon and requested action through both GatewayPlugin (ADK adapter)
and create_proxy_app (non-ADK proxy stub adapter) to prove that the underlying policy
enforcement core (gateway.policy.evaluate) is framework-agnostic.
See AGENTS.md §Testing conventions and agent-specification.md §13.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.adapters.adk_plugin import GatewayPlugin
from gateway.adapters.proxy_stub import create_proxy_app
from macaroon.attenuate import attenuate
from macaroon.issue import issue_root_macaroon
from registry.agents_registry import AgentRegistry


@pytest.fixture
def shared_environment() -> dict[str, Any]:
    """Provide a single shared root key, single AgentRegistry instance, and both adapters."""
    root_key = b"shared-root-key-for-adapter-equivalence-test"
    registry = AgentRegistry()
    registry.register(
        agent_id="orchestrator_agent",
        display_name="Orchestrator",
        max_scope={"read", "fetch", "delete"},
        owner="sec-team",
    )
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher",
        max_scope={"read", "fetch"},
        owner="sec-team",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="sec-team",
    )

    plugin = GatewayPlugin(
        root_key=root_key,
        registry=registry,
        initial_scope={"read", "fetch", "delete"},
    )
    proxy_app = create_proxy_app(root_key=root_key, registry=registry)
    client = TestClient(proxy_app)

    return {
        "root_key": root_key,
        "registry": registry,
        "plugin": plugin,
        "client": client,
    }


@pytest.mark.asyncio
async def test_equivalence_allowed_scenario(
    shared_environment: dict[str, Any],
) -> None:
    """Assert ADK plugin and proxy stub both allow in-scope action with identical decision."""
    root_key: bytes = shared_environment["root_key"]
    registry: AgentRegistry = shared_environment["registry"]
    plugin: GatewayPlugin = shared_environment["plugin"]
    client: TestClient = shared_environment["client"]

    # Issue root token with read, delete scope, attenuate to tool_caller_agent for read
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read", "delete"},
        root_key=root_key,
        chain_id="chain-equiv-100",
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )
    token_str = delegated.serialize()

    # 1. ADK Adapter execution
    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": token_str},
    )
    adk_result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={"record_id": "rec-1"},
        tool_context=tool_context,  # type: ignore[arg-type]
    )
    adk_allowed = adk_result is None
    adk_reason = "allowed" if adk_result is None else adk_result.get("reason")

    # 2. Proxy Stub Adapter execution
    proxy_response = client.post(
        "/evaluate",
        json={
            "macaroon": token_str,
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )
    assert proxy_response.status_code == 200
    proxy_data = proxy_response.json()
    proxy_allowed = proxy_data["allowed"]
    proxy_reason = proxy_data["reason"]

    # Assert exact equivalence
    assert proxy_allowed is True
    assert adk_allowed is True
    assert proxy_allowed == adk_allowed
    assert proxy_reason == adk_reason == "allowed"
    assert proxy_data["chain_id"] == "chain-equiv-100"


@pytest.mark.asyncio
async def test_equivalence_denied_out_of_scope(
    shared_environment: dict[str, Any],
) -> None:
    """Assert ADK plugin and proxy stub both deny out-of-scope action with identical reason."""
    root_key: bytes = shared_environment["root_key"]
    registry: AgentRegistry = shared_environment["registry"]
    plugin: GatewayPlugin = shared_environment["plugin"]
    client: TestClient = shared_environment["client"]

    # Issue root token with read only, attenuate to tool_caller_agent with read
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read only task",
        initial_scope={"read"},
        root_key=root_key,
        chain_id="chain-equiv-200",
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )
    token_str = delegated.serialize()

    # 1. ADK Adapter execution (attempt delete_record -> mapped to "delete")
    tool = SimpleNamespace(name="delete_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": token_str},
    )
    adk_result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={"record_id": "rec-1"},
        tool_context=tool_context,  # type: ignore[arg-type]
    )
    assert isinstance(adk_result, dict)
    adk_allowed = False
    adk_reason = adk_result.get("reason")

    # 2. Proxy Stub Adapter execution (attempt "delete")
    proxy_response = client.post(
        "/evaluate",
        json={
            "macaroon": token_str,
            "requested_action": "delete",
            "presenting_agent_id": "tool_caller_agent",
        },
    )
    assert proxy_response.status_code == 200
    proxy_data = proxy_response.json()
    proxy_allowed = proxy_data["allowed"]
    proxy_reason = proxy_data["reason"]

    # Assert exact equivalence
    assert proxy_allowed is False
    assert adk_allowed is False
    assert proxy_allowed == adk_allowed
    assert proxy_reason == adk_reason
    assert proxy_reason == "scope caveat violated: requested=delete, allowed=read"


@pytest.mark.asyncio
async def test_equivalence_denied_missing_macaroon(
    shared_environment: dict[str, Any],
) -> None:
    """Assert ADK plugin and proxy stub both deny missing token with identical reason."""
    plugin: GatewayPlugin = shared_environment["plugin"]
    client: TestClient = shared_environment["client"]

    # 1. ADK Adapter execution (empty state)
    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={},
    )
    adk_result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )
    assert isinstance(adk_result, dict)
    adk_allowed = False
    adk_reason = adk_result.get("reason")

    # 2. Proxy Stub Adapter execution (macaroon = None)
    proxy_response = client.post(
        "/evaluate",
        json={
            "macaroon": None,
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )
    assert proxy_response.status_code == 200
    proxy_data = proxy_response.json()
    proxy_allowed = proxy_data["allowed"]
    proxy_reason = proxy_data["reason"]

    # Assert exact equivalence
    assert proxy_allowed is False
    assert adk_allowed is False
    assert proxy_allowed == adk_allowed
    assert proxy_reason == adk_reason
    assert proxy_reason == "no macaroon presented"


@pytest.mark.asyncio
async def test_equivalence_denied_malformed_macaroon(
    shared_environment: dict[str, Any],
) -> None:
    """Assert ADK plugin and proxy stub both deny malformed token with identical reason."""
    plugin: GatewayPlugin = shared_environment["plugin"]
    client: TestClient = shared_environment["client"]
    malformed_token = "gibberish-not-a-valid-serialized-macaroon-token-12345"

    # 1. ADK Adapter execution
    tool = SimpleNamespace(name="read_record")
    tool_context = SimpleNamespace(
        agent_name="tool_caller_agent",
        state={"agent_macaroon": malformed_token},
    )
    adk_result = await plugin.before_tool_callback(
        tool=tool,  # type: ignore[arg-type]
        tool_args={},
        tool_context=tool_context,  # type: ignore[arg-type]
    )
    assert isinstance(adk_result, dict)
    adk_allowed = False
    adk_reason = adk_result.get("reason")

    # 2. Proxy Stub Adapter execution
    proxy_response = client.post(
        "/evaluate",
        json={
            "macaroon": malformed_token,
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )
    assert proxy_response.status_code == 200
    proxy_data = proxy_response.json()
    proxy_allowed = proxy_data["allowed"]
    proxy_reason = proxy_data["reason"]

    # Assert exact equivalence
    assert proxy_allowed is False
    assert adk_allowed is False
    assert proxy_allowed == adk_allowed
    assert proxy_reason == adk_reason
    assert proxy_reason == "no macaroon presented"
