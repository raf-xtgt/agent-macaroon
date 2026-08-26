"""Unit tests for FastAPI audit replay API routes (F6) and merged ADK app serving."""

import os
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

# Ensure root key and GCP project exist for test environment
os.environ.setdefault("AGENT_MACAROON_ROOT_KEY", "test_secret_root_key_123")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from audit.trace import Span
from main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    """Assert /health endpoint returns 200 and ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_replay_200_success() -> None:
    """Assert GET /audit/replay returns structured JSON timeline matching §8 schema."""
    ts1 = datetime(2026, 8, 19, 14, 2, 3, 101000, tzinfo=timezone.utc)
    ts2 = datetime(2026, 8, 19, 14, 2, 3, 340000, tzinfo=timezone.utc)

    mock_spans = [
        Span(
            span_id="s-0",
            parent_span_id=None,
            chain_id="chain-7f3a",
            agent_id="orchestrator_agent",
            macaroon_identifier_hash="hash-root",
            action_requested="issue_macaroon",
            decision="allow",
            reason="root macaroon issued",
            timestamp=ts1,
            human_subject_id="alice@example.com",
            purpose="book a flight to SFO",
        ),
        Span(
            span_id="s-1",
            parent_span_id="s-0",
            chain_id="chain-7f3a",
            agent_id="researcher_agent",
            macaroon_identifier_hash="hash-att1",
            action_requested="transfer_to_agent",
            decision="allow",
            reason="attenuated",
            timestamp=ts2,
            human_subject_id=None,
            purpose=None,
        ),
    ]

    with patch("audit.api.get_chain_spans", return_value=mock_spans):
        response = client.get("/audit/replay?chain_id=chain-7f3a")

    assert response.status_code == 200
    data = response.json()
    assert data["chain_id"] == "chain-7f3a"
    assert data["human_subject_id"] == "alice@example.com"
    assert data["purpose"] == "book a flight to SFO"
    assert data["started_at"] == ts1.isoformat()
    assert data["hop_count"] == 2
    assert data["verdict"] == "allowed"
    assert len(data["spans"]) == 2
    assert data["spans"][0]["span_id"] == "s-0"
    assert data["spans"][1]["parent_span_id"] == "s-0"


def test_get_replay_404_not_found() -> None:
    """Assert GET /audit/replay returns 404 when no spans exist for chain_id."""
    with patch("audit.api.get_chain_spans", return_value=[]):
        response = client.get("/audit/replay?chain_id=non-existent")

    assert response.status_code == 404
    data = response.json()
    assert "no spans found for chain_id non-existent" in data["detail"]


def test_merged_app_serves_orchestrator_agent() -> None:
    """Assert the merged FastAPI app exposes ADK agent-serving endpoints for orchestrator."""
    list_response = client.get("/list-apps")
    assert list_response.status_code == 200
    apps = list_response.json()
    assert "orchestrator" in apps

    info_response = client.get("/apps/orchestrator/app-info")
    assert info_response.status_code == 200
    info_data = info_response.json()
    assert info_data["name"] == "orchestrator"
    assert info_data["rootAgentName"] == "orchestrator_agent"
    assert "orchestrator_agent" in info_data["agents"]
    assert "researcher_agent" in info_data["agents"]
    assert "tool_caller_agent" in info_data["agents"]


def test_armor_status_endpoint() -> None:
    """Assert /armor/status returns active pattern count and runtime patterns."""
    response = client.get("/armor/status")
    assert response.status_code == 200
    data = response.json()
    assert "active_pattern_count" in data
    assert data["active_pattern_count"] >= 12
    assert "runtime_patterns" in data
    assert isinstance(data["runtime_patterns"], list)
