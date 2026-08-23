"""Unit tests for orchestrator App wiring, GatewayPlugin registration, and root key loading."""

import os
import subprocess
import sys
from pathlib import Path

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
    assert plugin._initial_scope == {"read", "fetch", "delete", "delegate"}

    # Verify registry scope ceilings
    registry = plugin._registry
    assert registry.ceiling("orchestrator_agent") == frozenset(
        {"read", "fetch", "delete", "delegate"}
    )
    assert registry.ceiling("researcher_agent") == frozenset(
        {"read", "fetch", "delegate"}
    )
    assert registry.ceiling("tool_caller_agent") == frozenset({"read", "delete"})


def test_orchestrator_package_reexports() -> None:
    """Assert that agents.orchestrator re-exports app, orchestrator_agent, and root_agent."""
    assert pkg_app is app
    assert pkg_orchestrator_agent is orchestrator_agent
    assert pkg_root_agent is root_agent


def test_import_missing_root_key_subprocess_fails_cleanly() -> None:
    """Assert importing agents.orchestrator.agent without AGENT_MACAROON_ROOT_KEY fails cleanly.

    Verifies the subprocess raises RuntimeError for missing AGENT_MACAROON_ROOT_KEY
    and does NOT raise ValidationError ('already has a parent agent') caused by
    singleton sub-agent mutation before root key validation.
    """
    backend_dir = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "AGENT_MACAROON_ROOT_KEY"}
    env["PYTHONPATH"] = str(backend_dir)

    proc = subprocess.run(
        [sys.executable, "-c", "import agents.orchestrator.agent"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )

    assert proc.returncode != 0
    assert "RuntimeError" in proc.stderr
    assert "AGENT_MACAROON_ROOT_KEY" in proc.stderr
    assert "ValidationError" not in proc.stderr
    assert "already has a parent" not in proc.stderr


def test_import_valid_root_key_subprocess_succeeds() -> None:
    """Assert importing agents.orchestrator.agent in a clean subprocess succeeds when key is set."""
    backend_dir = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "AGENT_MACAROON_ROOT_KEY": "test_secret_key_123",
        "PYTHONPATH": str(backend_dir),
    }

    proc = subprocess.run(
        [sys.executable, "-c", "import agents.orchestrator.agent"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )

    assert proc.returncode == 0
    assert "RuntimeError" not in proc.stderr
    assert "ValidationError" not in proc.stderr
