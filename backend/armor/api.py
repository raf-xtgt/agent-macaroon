"""FastAPI router for Model Armor immunization status and manual operations."""

from typing import Any

from fastapi import APIRouter

from armor.screen import get_active_pattern_count, list_runtime_patterns

router = APIRouter(prefix="/armor", tags=["model-armor"])


@router.get("/status")
def armor_status() -> dict[str, Any]:
    """Return current Model Armor status: pattern counts and runtime patterns."""
    return {
        "active_pattern_count": get_active_pattern_count(),
        "runtime_patterns": list_runtime_patterns(),
    }
