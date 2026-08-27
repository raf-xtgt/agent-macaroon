"""Google Model Armor (Vertex AI) integration for ML-based injection screening.

Uses the google-cloud-modelarmor SDK to call Google's server-side prompt
injection and jailbreak detector. This is the deep ML layer that complements
the fast local regex layer in armor/screen.py.
"""

import os
from dataclasses import dataclass
from typing import Any

import google.cloud.modelarmor_v1 as ma


@dataclass(frozen=True)
class ModelArmorResult:
    """Result from Google Model Armor API screening.

    Attributes:
        flagged: True if prompt injection, jailbreak, or RAI violation was detected.
        match_state: String representation of filter match state ("MATCH_FOUND", "NO_MATCH_FOUND", or "ERROR").
        confidence_level: Detection confidence level name (e.g. "LOW_AND_ABOVE", "MEDIUM_AND_ABOVE", "HIGH", or None).
        pi_and_jailbreak_detected: True if prompt injection and jailbreak filter matched.
        rai_flagged: True if responsible AI filter matched.
        raw_filter_results: Dictionary containing raw breakdown for audit spans, or None on error.
        error: Error message string if an API exception occurred, otherwise None.
    """

    flagged: bool
    match_state: str
    confidence_level: str | None
    pi_and_jailbreak_detected: bool
    rai_flagged: bool
    raw_filter_results: dict[str, Any] | None
    error: str | None


_client: ma.ModelArmorClient | None = None


def _get_client() -> ma.ModelArmorClient:
    """Get or lazily initialize the singleton Model Armor client."""
    global _client
    if _client is None:
        _client = ma.ModelArmorClient()
    return _client


def _get_template_name() -> str:
    """Build the full template resource name from environment variables.

    Requires:
        GOOGLE_CLOUD_PROJECT — the GCP project ID
        GOOGLE_CLOUD_LOCATION — the location (default: "global")
        MODEL_ARMOR_TEMPLATE_ID — the template ID (default: "agent-macaroon-screen")
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    template_id = os.environ.get("MODEL_ARMOR_TEMPLATE_ID", "agent-macaroon-screen")
    return f"projects/{project}/locations/{location}/templates/{template_id}"


def ensure_template_exists() -> str:
    """Create the Model Armor template if it does not exist. Return the template name.

    The template enables:
    - Prompt injection and jailbreak detection (LOW_AND_ABOVE confidence)
    - RAI filtering for DANGEROUS content (MEDIUM_AND_ABOVE confidence)

    If the template already exists, this is a no-op (returns the existing name).
    If creation fails (e.g., API not enabled, permissions), returns the name anyway
    and lets the sanitize call fail later with a clear error.
    """
    template_name = _get_template_name()
    try:
        client = _get_client()
        # Check if template exists
        try:
            client.get_template(request=ma.GetTemplateRequest(name=template_name))
            return template_name
        except Exception:  # noqa: BLE001, S110
            pass  # Template doesn't exist, create it

        # Parse parent from template name: "projects/X/locations/Y/templates/Z" -> "projects/X/locations/Y"
        parts = template_name.rsplit("/templates/", 1)
        parent = parts[0]
        template_id = parts[1] if len(parts) > 1 else "agent-macaroon-screen"

        enforcement_cls = getattr(
            ma.PiAndJailbreakFilterSettings,
            "FilterEnforcement",
            getattr(
                ma.PiAndJailbreakFilterSettings,
                "PiAndJailbreakFilterEnforcement",
                None,
            ),
        )
        enforcement_val = (
            getattr(enforcement_cls, "ENABLED", 1) if enforcement_cls else 1
        )

        template = ma.Template(
            filter_config=ma.FilterConfig(
                pi_and_jailbreak_filter_settings=ma.PiAndJailbreakFilterSettings(
                    filter_enforcement=enforcement_val,
                    confidence_level=ma.DetectionConfidenceLevel.LOW_AND_ABOVE,
                ),
                rai_settings=ma.RaiFilterSettings(
                    rai_filters=[
                        ma.RaiFilterSettings.RaiFilter(
                            filter_type=ma.RaiFilterType.DANGEROUS,
                            confidence_level=ma.DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
                        ),
                    ]
                ),
            ),
        )

        try:
            client.create_template(
                request=ma.CreateTemplateRequest(
                    parent=parent,
                    template_id=template_id,
                    template=template,
                )
            )
        except Exception:  # noqa: BLE001, S110
            pass  # Creation may fail (already exists race, permissions, etc.)
    except Exception:  # noqa: BLE001, S110
        pass

    return template_name


def screen_with_model_armor(text: str) -> ModelArmorResult:
    """Screen text using Google Model Armor's ML-based detection.

    Uses SanitizeModelResponseRequest because we are screening tool outputs
    (model/agent responses), not user prompts.

    Args:
        text: The text content to screen.

    Returns:
        ModelArmorResult with detection results and confidence levels.
    """
    try:
        client = _get_client()
        template_name = _get_template_name()

        request = ma.SanitizeModelResponseRequest(
            name=template_name,
            model_response_data=ma.DataItem(text=text),
        )
        response = client.sanitize_model_response(request=request)

        result = getattr(response, "sanitization_result", None)
        overall_match = getattr(result, "filter_match_state", None)

        filter_results = getattr(result, "filter_results", None)
        pi_result = (
            getattr(filter_results, "pi_and_jailbreak_filter_result", None)
            if filter_results
            else None
        )
        pi_detected = False
        pi_confidence = None
        if pi_result is not None:
            match_state_val = getattr(pi_result, "match_state", None)
            pi_detected = match_state_val == ma.FilterMatchState.MATCH_FOUND
            raw_conf = getattr(pi_result, "confidence_level", None)
            if pi_detected and raw_conf is not None:
                try:
                    pi_confidence = ma.DetectionConfidenceLevel(raw_conf).name
                except (ValueError, TypeError):
                    pi_confidence = str(raw_conf)

        rai_result = (
            getattr(filter_results, "rai_filter_result", None)
            if filter_results
            else None
        )
        rai_flagged = False
        if rai_result is not None:
            if (
                hasattr(rai_result, "rai_filter_type_results")
                and rai_result.rai_filter_type_results
            ):
                type_results = rai_result.rai_filter_type_results
                if isinstance(type_results, dict):
                    type_results = type_results.values()
                for type_result in type_results:
                    if (
                        getattr(type_result, "match_state", None)
                        == ma.FilterMatchState.MATCH_FOUND
                    ):
                        rai_flagged = True
                        break
            elif (
                getattr(rai_result, "match_state", None)
                == ma.FilterMatchState.MATCH_FOUND
            ):
                rai_flagged = True

        flagged = (
            (overall_match == ma.FilterMatchState.MATCH_FOUND)
            or pi_detected
            or rai_flagged
        )

        match_state_str = "UNKNOWN"
        if overall_match is not None:
            try:
                match_state_str = ma.FilterMatchState(overall_match).name
            except (ValueError, TypeError):
                match_state_str = str(overall_match)
        elif flagged:
            match_state_str = "MATCH_FOUND"
        else:
            match_state_str = "NO_MATCH_FOUND"

        raw_results = {
            "overall_match_state": match_state_str,
            "pi_and_jailbreak": {
                "detected": pi_detected,
                "confidence": pi_confidence,
            },
            "rai": {
                "flagged": rai_flagged,
            },
        }

        return ModelArmorResult(
            flagged=flagged,
            match_state=match_state_str,
            confidence_level=pi_confidence,
            pi_and_jailbreak_detected=pi_detected,
            rai_flagged=rai_flagged,
            raw_filter_results=raw_results,
            error=None,
        )

    except Exception as exc:  # noqa: BLE001
        return ModelArmorResult(
            flagged=False,
            match_state="ERROR",
            confidence_level=None,
            pi_and_jailbreak_detected=False,
            rai_flagged=False,
            raw_filter_results=None,
            error=f"{type(exc).__name__}: {exc}",
        )
