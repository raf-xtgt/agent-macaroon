"""FastAPI router for Model Armor immunization status and manual operations."""

import os
from typing import Any

from fastapi import APIRouter

from armor.model_armor import _get_template_name
from armor.screen import get_active_pattern_count, list_runtime_patterns

router = APIRouter(prefix="/armor", tags=["model-armor"])


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
