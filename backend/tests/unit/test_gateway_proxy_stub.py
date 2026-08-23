"""Unit tests for the non-ADK proxy stub adapter (gateway/adapters/proxy_stub.py)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.adapters.proxy_stub import _build_default_registry, create_proxy_app
from macaroon.attenuate import attenuate
from macaroon.issue import issue_root_macaroon
from registry.agents_registry import AgentRegistry


@pytest.fixture
def proxy_setup() -> dict[str, Any]:
    """Fixture providing initialized root key, registry, and test client."""
    root_key = b"proxy-test-secret-root-key"
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
    app = create_proxy_app(root_key=root_key, registry=registry)
    client = TestClient(app)
    return {
        "root_key": root_key,
        "registry": registry,
        "app": app,
        "client": client,
    }


def test_build_default_registry() -> None:
    """Assert _build_default_registry registers all 3 agents with exact required ceilings."""
    registry = _build_default_registry()

    assert registry.ceiling("orchestrator_agent") == frozenset(
        {"read", "fetch", "delete"}
    )
    assert registry.ceiling("researcher_agent") == frozenset({"read", "fetch"})
    assert registry.ceiling("tool_caller_agent") == frozenset({"read", "delete"})
    assert registry.ceiling("unknown_agent") == frozenset()


def test_create_proxy_app(proxy_setup: dict[str, Any]) -> None:
    """Assert create_proxy_app returns a valid FastAPI app instance with /evaluate route."""
    app = proxy_setup["app"]
    assert isinstance(app, FastAPI)

    route_paths = [route.path for route in app.routes]  # type: ignore[union-attr]
    assert "/evaluate" in route_paths


def test_proxy_stub_allow_valid_macaroon(proxy_setup: dict[str, Any]) -> None:
    """Assert in-scope action with valid attenuated macaroon returns 200 with allowed=True."""
    root_key = proxy_setup["root_key"]
    registry = proxy_setup["registry"]
    client: TestClient = proxy_setup["client"]

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read", "delete"},
        root_key=root_key,
        chain_id="chain-test-111",
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    response = client.post(
        "/evaluate",
        json={
            "macaroon": delegated.serialize(),
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["reason"] == "allowed"
    assert data["requested_action"] == "read"
    assert data["presenting_agent_id"] == "tool_caller_agent"
    assert data["chain_id"] == "chain-test-111"
    assert data["macaroon_identifier_hash"] is not None
    assert "timestamp" in data


def test_proxy_stub_deny_out_of_scope(proxy_setup: dict[str, Any]) -> None:
    """Assert out-of-scope action with valid macaroon returns 200 with allowed=False and reason."""
    root_key = proxy_setup["root_key"]
    registry = proxy_setup["registry"]
    client: TestClient = proxy_setup["client"]

    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read-only task",
        initial_scope={"read"},
        root_key=root_key,
        chain_id="chain-test-222",
    )
    delegated = attenuate(
        macaroon=macaroon,
        to_agent_id="tool_caller_agent",
        task_required_scope={"read"},
        registry=registry,
    )

    response = client.post(
        "/evaluate",
        json={
            "macaroon": delegated.serialize(),
            "requested_action": "delete",
            "presenting_agent_id": "tool_caller_agent",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert data["reason"] == "scope caveat violated: requested=delete, allowed=read"
    assert data["requested_action"] == "delete"
    assert data["presenting_agent_id"] == "tool_caller_agent"
    assert data["chain_id"] == "chain-test-222"


def test_proxy_stub_deny_null_macaroon(proxy_setup: dict[str, Any]) -> None:
    """Assert null/missing macaroon returns 200 with allowed=False without throwing transport error."""
    client: TestClient = proxy_setup["client"]

    response = client.post(
        "/evaluate",
        json={
            "macaroon": None,
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert "no macaroon presented" in data["reason"]
    assert data["macaroon_identifier_hash"] is None
    assert data["chain_id"] is None


def test_proxy_stub_deny_malformed_macaroon(proxy_setup: dict[str, Any]) -> None:
    """Assert garbage macaroon string is caught safely and returns 200 allowed=False."""
    client: TestClient = proxy_setup["client"]

    response = client.post(
        "/evaluate",
        json={
            "macaroon": "not-a-valid-serialized-macaroon-string-@@@!",
            "requested_action": "read",
            "presenting_agent_id": "tool_caller_agent",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert "no macaroon presented" in data["reason"]
    assert data["macaroon_identifier_hash"] is None
    assert data["chain_id"] is None


def test_proxy_stub_validation_error_missing_action(
    proxy_setup: dict[str, Any],
) -> None:
    """Assert missing requested_action triggers standard FastAPI 422 validation error."""
    client: TestClient = proxy_setup["client"]

    response = client.post(
        "/evaluate",
        json={
            "presenting_agent_id": "tool_caller_agent",
        },
    )

    assert response.status_code == 422


def test_proxy_stub_validation_error_missing_agent_id(
    proxy_setup: dict[str, Any],
) -> None:
    """Assert missing presenting_agent_id triggers standard FastAPI 422 validation error."""
    client: TestClient = proxy_setup["client"]

    response = client.post(
        "/evaluate",
        json={
            "requested_action": "read",
        },
    )

    assert response.status_code == 422


def test_proxy_stub_cli_refuses_adk_mode() -> None:
    """Assert running proxy_stub as script with GATEWAY_MODE=adk exits non-zero with clear error."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "GATEWAY_MODE": "adk",
        "PYTHONPATH": str(backend_dir),
    }

    proc = subprocess.run(
        [sys.executable, "-m", "gateway.adapters.proxy_stub"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )

    assert proc.returncode != 0
    assert "Refusing to start proxy stub" in proc.stderr
    assert "GATEWAY_MODE is 'adk'" in proc.stderr


def test_proxy_stub_cli_missing_root_key_raises_runtime_error() -> None:
    """Assert running proxy_stub with GATEWAY_MODE=proxy but missing root key raises RuntimeError."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "AGENT_MACAROON_ROOT_KEY"}
    env["GATEWAY_MODE"] = "proxy"
    env["PYTHONPATH"] = str(backend_dir)

    proc = subprocess.run(
        [sys.executable, "-m", "gateway.adapters.proxy_stub"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )

    assert proc.returncode != 0
    assert "RuntimeError" in proc.stderr
    assert "AGENT_MACAROON_ROOT_KEY" in proc.stderr
