"""FastAPI router for Model Armor immunization status, live tuning, and defense profile export."""

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from armor.model_armor import (
    _get_template_name,
    get_template_config,
    tune_template,
)
from armor.screen import (
    add_runtime_pattern,
    get_active_pattern_count,
    list_runtime_patterns,
)
from audit.trace import emit_span

router = APIRouter(prefix="/armor", tags=["model-armor"])

_ALLOWED_CONFIDENCE = {"LOW_AND_ABOVE", "MEDIUM_AND_ABOVE", "HIGH"}
_ALLOWED_RAI_TYPES = {"DANGEROUS", "HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT"}
_ALLOWED_ENFORCEMENT = {"INSPECT_AND_BLOCK", "INSPECT_ONLY"}

# Seed runtime patterns targeting context_manipulation evasion technique.
# These catch adversarial directives hidden in AML/KYC compliance framing
# that evade both static regex and Model Armor ML classification.
_SEED_PATTERNS = [
    (
        "tuned_compliance_directive",
        r"(?:pursuant\s+to|in\s+accordance\s+with|under\s+the).*?(?:you\s+must|must\s+now|also\s+call|also\s+retrieve|incorporate\s+the\s+above)",
    ),
    (
        "tuned_reference_item",
        r"reference\s+item\s+\d[\d.]*\s*:.*?(?:call|retrieve|execute|invoke|get_|search_|fetch)",
    ),
    (
        "tuned_operational_requirement",
        r"(?:operational\s+requirement|mandatory\s+review\s+note|compliance\s+data)\s*:.*?(?:must|should|need\s+to|call|retrieve|suppress|override)",
    ),
]


class RaiFilterItem(BaseModel):
    """Configuration for an individual Responsible AI filter."""

    type: str
    confidence_level: str


class TuneRequest(BaseModel):
    """Request model for tuning Model Armor filter configuration."""

    pi_and_jailbreak_enabled: bool = True
    pi_and_jailbreak_confidence: str = "LOW_AND_ABOVE"
    rai_filters: list[RaiFilterItem] = []
    enforcement_type: str = "INSPECT_AND_BLOCK"
    multi_language_detection: bool = True
    malicious_uri: bool = True
    sdp_basic: bool = False


@router.get("/status")
def armor_status() -> dict[str, Any]:
    """Return current Model Armor status: pattern counts and runtime patterns."""
    ma_available = False
    ma_template = None
    try:
        ma_template = _get_template_name()
        # Don't actually call the API on every status check — just report config
        ma_available = bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    except Exception:  # noqa: BLE001, S110
        pass

    return {
        "active_pattern_count": get_active_pattern_count(),
        "runtime_patterns": list_runtime_patterns(),
        "model_armor": {
            "enabled": ma_available,
            "template": ma_template,
        },
    }


@router.get("/config")
def armor_config() -> dict[str, Any]:
    """Return the normalized Model Armor filter configuration."""
    return get_template_config()


@router.post("/tune")
def armor_tune(request: TuneRequest) -> dict[str, Any]:
    """Update live Model Armor template configuration.

    Validates confidence levels, responsible AI filter types, and enforcement settings
    before applying changes via the Model Armor API. Also seeds runtime regex patterns
    targeting context_manipulation evasion techniques.
    """
    if request.pi_and_jailbreak_confidence not in _ALLOWED_CONFIDENCE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid pi_and_jailbreak_confidence '{request.pi_and_jailbreak_confidence}'. "
                f"Must be one of: {sorted(_ALLOWED_CONFIDENCE)}"
            ),
        )

    if request.enforcement_type not in _ALLOWED_ENFORCEMENT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid enforcement_type '{request.enforcement_type}'. "
                f"Must be one of: {sorted(_ALLOWED_ENFORCEMENT)}"
            ),
        )

    for idx, rf in enumerate(request.rai_filters):
        if rf.type not in _ALLOWED_RAI_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid rai_filter[{idx}].type '{rf.type}'. "
                    f"Must be one of: {sorted(_ALLOWED_RAI_TYPES)}"
                ),
            )
        if rf.confidence_level not in _ALLOWED_CONFIDENCE:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid rai_filter[{idx}].confidence_level '{rf.confidence_level}'. "
                    f"Must be one of: {sorted(_ALLOWED_CONFIDENCE)}"
                ),
            )

    result = tune_template(request.model_dump())
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get(
                "error", "Failed to update Model Armor template via GCP SDK"
            ),
        )

    # Seed runtime patterns targeting context_manipulation evasion if not already present.
    existing_patterns = set(list_runtime_patterns())
    seeded: list[str] = []
    for name, pattern in _SEED_PATTERNS:
        if name not in existing_patterns:
            add_runtime_pattern(name, pattern)
            seeded.append(name)

    if seeded:
        emit_span(
            chain_id=None,
            parent_span_id=None,
            agent_id="red_team:tuner",
            macaroon_identifier_hash=None,
            action_requested="seed_patterns",
            decision="allow",
            reason=f"Seeded {len(seeded)} runtime patterns targeting context_manipulation evasion.",
        )

    return {
        **result,
        "seeded_patterns": [
            name for name, _ in _SEED_PATTERNS if name in set(list_runtime_patterns())
        ],
    }


@router.get("/export")
def armor_export() -> dict[str, Any]:
    """Serialize and export the full capability and defense posture as JSON.

    Gathers registry scope ceilings, tool action verb mappings, Model Armor configuration,
    runtime immunization patterns, and gateway boundaries. Contains zero secret material.
    """
    # 1. Registry ceilings
    ceilings: dict[str, list[str]] = {}
    try:
        from agents.governed.agent import registry

        for agent_id in registry.list_agents():
            ceilings[agent_id] = sorted(registry.ceiling(agent_id))
    except Exception:  # noqa: BLE001, S110
        pass

    # 2. Tool action map and Gateway Plugin attributes
    tool_action_map: dict[str, str] = {}
    initial_scope: list[str] = []
    max_depth = 21
    enable_model_armor = True
    entry_agent_id = "global_kyc_agent"
    try:
        from agents.governed.agent import app as governed_app

        for plugin in getattr(governed_app, "plugins", []):
            if hasattr(plugin, "_tool_action_map"):
                tool_action_map = dict(sorted(plugin._tool_action_map.items()))
            if hasattr(plugin, "_initial_scope"):
                initial_scope = sorted(plugin._initial_scope)
            if hasattr(plugin, "_max_depth"):
                max_depth = plugin._max_depth
            if hasattr(plugin, "_enable_model_armor"):
                enable_model_armor = plugin._enable_model_armor
            if hasattr(plugin, "_entry_agent_id"):
                entry_agent_id = plugin._entry_agent_id
    except Exception:  # noqa: BLE001, S110
        pass

    # 3. Model Armor configuration
    ma_config = get_template_config()
    ma_template_id = os.environ.get("MODEL_ARMOR_TEMPLATE_ID", "agent-macaroon-screen")

    # 4. Runtime immunization patterns
    runtime_patterns = list_runtime_patterns()
    active_pattern_count = get_active_pattern_count()

    target_fleet = os.environ.get("TARGET_FLEET_PACKAGE", "global_kyc_agent")

    return {
        "agent_macaroon_config": {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_fleet": target_fleet,
            "fleet_summary": {
                "agent_count": len(ceilings),
                "tool_count": len(tool_action_map),
            },
            "gateway_plugin": {
                "max_depth": max_depth,
                "enable_model_armor": enable_model_armor,
                "entry_agent_id": entry_agent_id,
            },
            "initial_scope": initial_scope,
            "registry_ceilings": ceilings,
            "tool_action_map": tool_action_map,
            "model_armor": {
                "template_id": ma_template_id,
                "config": ma_config,
            },
            "immunization": {
                "runtime_pattern_count": len(runtime_patterns),
                "runtime_patterns": runtime_patterns,
                "total_active_patterns": active_pattern_count,
            },
        }
    }
