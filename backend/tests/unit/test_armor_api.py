"""Unit tests for Model Armor FastAPI endpoints (GET /armor/config, POST /armor/tune, GET /armor/export, GET /armor/status)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_get_armor_status() -> None:
    """Assert GET /armor/status returns pattern counts and Model Armor metadata."""
    response = client.get("/armor/status")
    assert response.status_code == 200
    data = response.json()
    assert "active_pattern_count" in data
    assert "runtime_patterns" in data
    assert "model_armor" in data
    assert isinstance(data["runtime_patterns"], list)


def test_get_armor_config() -> None:
    """Assert GET /armor/config returns the normalized Model Armor configuration."""
    mock_config = {
        "pi_and_jailbreak_enabled": True,
        "pi_and_jailbreak_confidence": "HIGH",
        "rai_filters": [{"type": "DANGEROUS", "confidence_level": "LOW_AND_ABOVE"}],
        "enforcement_type": "INSPECT_AND_BLOCK",
        "multi_language_detection": True,
        "malicious_uri": True,
        "sdp_basic": False,
    }
    with patch("armor.api.get_template_config", return_value=mock_config):
        response = client.get("/armor/config")
        assert response.status_code == 200
        assert response.json() == mock_config


def test_post_armor_tune_valid() -> None:
    """Assert POST /armor/tune with valid config calls tune_template and returns 200."""
    payload = {
        "pi_and_jailbreak_enabled": True,
        "pi_and_jailbreak_confidence": "HIGH",
        "rai_filters": [
            {"type": "DANGEROUS", "confidence_level": "LOW_AND_ABOVE"},
            {"type": "HARASSMENT", "confidence_level": "MEDIUM_AND_ABOVE"},
        ],
        "enforcement_type": "INSPECT_ONLY",
        "multi_language_detection": True,
        "malicious_uri": True,
        "sdp_basic": False,
    }

    mock_applied = {
        "success": True,
        "applied_config": payload,
        "error": None,
    }

    with patch("armor.api.tune_template", return_value=mock_applied):
        response = client.post("/armor/tune", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["applied_config"]["pi_and_jailbreak_confidence"] == "HIGH"


def test_post_armor_tune_invalid_confidence() -> None:
    """Assert POST /armor/tune with invalid confidence returns 400."""
    payload = {
        "pi_and_jailbreak_confidence": "INVALID_CONFIDENCE",
    }
    response = client.post("/armor/tune", json=payload)
    assert response.status_code == 400
    assert "Invalid pi_and_jailbreak_confidence" in response.json()["detail"]


def test_post_armor_tune_invalid_rai_type() -> None:
    """Assert POST /armor/tune with invalid RAI filter type returns 400."""
    payload = {
        "rai_filters": [{"type": "UNSUPPORTED_TYPE", "confidence_level": "HIGH"}]
    }
    response = client.post("/armor/tune", json=payload)
    assert response.status_code == 400
    assert "Invalid rai_filter" in response.json()["detail"]


def test_post_armor_tune_invalid_enforcement() -> None:
    """Assert POST /armor/tune with invalid enforcement type returns 400."""
    payload = {
        "enforcement_type": "INVALID_ENFORCEMENT",
    }
    response = client.post("/armor/tune", json=payload)
    assert response.status_code == 400
    assert "Invalid enforcement_type" in response.json()["detail"]


def test_post_armor_tune_failed_backend() -> None:
    """Assert POST /armor/tune returns HTTP 500 when tune_template fails."""
    mock_failed = {
        "success": False,
        "applied_config": None,
        "error": "GCP Permission Denied",
    }
    with patch("armor.api.tune_template", return_value=mock_failed):
        response = client.post(
            "/armor/tune",
            json={"pi_and_jailbreak_confidence": "HIGH"},
        )
        assert response.status_code == 500
        data = response.json()
        assert "GCP Permission Denied" in data["detail"]


def test_post_armor_tune_malformed_rai_filter_pydantic_validation() -> None:
    """Assert POST /armor/tune returns HTTP 422 when rai_filters has malformed structure."""
    payload = {
        "rai_filters": [{"invalid_key": "val"}],
    }
    response = client.post("/armor/tune", json=payload)
    assert response.status_code == 422


def test_get_armor_export_structure() -> None:
    """Assert GET /armor/export returns complete defense posture without secrets."""
    response = client.get("/armor/export")
    assert response.status_code == 200
    data = response.json()

    assert "agent_macaroon_config" in data
    cfg = data["agent_macaroon_config"]

    assert cfg["version"] == "1.0"
    assert "generated_at" in cfg
    assert "target_fleet" in cfg
    assert "fleet_summary" in cfg
    assert "gateway_plugin" in cfg
    assert "initial_scope" in cfg
    assert "registry_ceilings" in cfg
    assert "tool_action_map" in cfg
    assert "model_armor" in cfg
    assert "immunization" in cfg

    # Verify JSON serialization types (lists, not sets)
    assert isinstance(cfg["initial_scope"], list)
    assert isinstance(cfg["registry_ceilings"], dict)
    for agent_id, ceiling_list in cfg["registry_ceilings"].items():
        assert isinstance(agent_id, str)
        assert isinstance(ceiling_list, list)

    assert isinstance(cfg["tool_action_map"], dict)
    assert isinstance(cfg["immunization"]["runtime_patterns"], list)


def test_get_armor_export_no_secrets() -> None:
    """Assert GET /armor/export contains zero secret key material."""
    response = client.get("/armor/export")
    assert response.status_code == 200
    text = response.text

    assert "AGENT_MACAROON_ROOT_KEY" not in text
    assert "root_key" not in text
    assert "hmac" not in text.lower() or "macaroon" in text.lower()
