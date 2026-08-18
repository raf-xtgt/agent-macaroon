"""Unit tests for orchestrator App wiring, GatewayPlugin registration, and root key loading."""

import pytest
from google.adk.apps import App

from agents.orchestrator import app as pkg_app
from agents.orchestrator import orchestrator_agent as pkg_orchestrator_agent
from agents.orchestrator import root_agent as pkg_root_agent
from agents.orchestrator.agent import (
    _load_root_key,
    app,
    orchestrator_agent,
    root_agent,
)
from gateway.adapters.adk_plugin import GatewayPlugin


def test_load_root_key_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert _load_root_key returns UTF-8 encoded bytes when env var is set."""
    monkeypatch.setenv("AGENT_MACAROON_ROOT_KEY", "super_secret_test_key_123")
    assert _load_root_key() == b"super_secret_test_key_123"


def test_load_root_key_missing_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert _load_root_key raises RuntimeError mentioning the env var name when unset."""
    monkeypatch.delenv("AGENT_MACAROON_ROOT_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        _load_root_key()
    assert "AGENT_MACAROON_ROOT_KEY" in str(exc_info.value)


def test_load_root_key_empty_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert _load_root_key raises RuntimeError mentioning the env var name when empty."""
    monkeypatch.setenv("AGENT_MACAROON_ROOT_KEY", "")
    with pytest.raises(RuntimeError) as exc_info:
        _load_root_key()
    assert "AGENT_MACAROON_ROOT_KEY" in str(exc_info.value)


def test_orchestrator_app_and_plugin_wiring() -> None:
    """Assert the App instance is properly wired with GatewayPlugin and exact scope ceilings."""
    assert isinstance(app, App)
    assert app.name == "agent_macaroon_governed_chain"
    assert app.root_agent is orchestrator_agent
    assert root_agent is orchestrator_agent

    # Verify plugin registration
    assert len(app.plugins) == 1
    plugin = app.plugins[0]
    assert isinstance(plugin, GatewayPlugin)

    # Verify initial scope
    assert plugin._initial_scope == {"read", "fetch", "delete"}

    # Verify registry scope ceilings
    registry = plugin._registry
    assert registry.ceiling("orchestrator_agent") == frozenset(
        {"read", "fetch", "delete"}
    )
    assert registry.ceiling("researcher_agent") == frozenset({"read", "fetch"})
    assert registry.ceiling("tool_caller_agent") == frozenset({"read", "delete"})


def test_orchestrator_package_reexports() -> None:
    """Assert that agents.orchestrator re-exports app, orchestrator_agent, and root_agent."""
    assert pkg_app is app
    assert pkg_orchestrator_agent is orchestrator_agent
    assert pkg_root_agent is root_agent
