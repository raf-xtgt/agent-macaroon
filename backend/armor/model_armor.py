"""Google Model Armor (Vertex AI) integration for ML-based injection screening.

Uses the google-cloud-modelarmor SDK to call Google's server-side prompt
injection and jailbreak detector. This is the deep ML layer that complements
the fast local regex layer in armor/screen.py.
"""

import os
from dataclasses import dataclass
from typing import Any

import google.cloud.modelarmor_v1 as ma
from google.protobuf.field_mask_pb2 import FieldMask


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


DEFAULT_TEMPLATE_CONFIG: dict[str, Any] = {
    "pi_and_jailbreak_enabled": True,
    "pi_and_jailbreak_confidence": "LOW_AND_ABOVE",
    "rai_filters": [
        {"type": "DANGEROUS", "confidence_level": "MEDIUM_AND_ABOVE"},
    ],
    "enforcement_type": "INSPECT_AND_BLOCK",
    "multi_language_detection": True,
    "malicious_uri": True,
    "sdp_basic": False,
}


def get_template_config() -> dict[str, Any]:
    """Retrieve the normalized Model Armor filter configuration.

    Fetches the live template from the Model Armor API and maps its settings
    to a standard dictionary. If the API call fails or template does not exist,
    returns the default configuration dictionary.
    """
    try:
        client = _get_client()
        template_name = _get_template_name()
        template = client.get_template(
            request=ma.GetTemplateRequest(name=template_name)
        )

        fc = getattr(template, "filter_config", None)
        tm = getattr(template, "template_metadata", None)

        # PI & Jailbreak
        pi_settings = (
            getattr(fc, "pi_and_jailbreak_filter_settings", None) if fc else None
        )
        pi_conf = "LOW_AND_ABOVE"
        pi_enabled = True
        if pi_settings:
            raw_conf = getattr(pi_settings, "confidence_level", None)
            if raw_conf:
                try:
                    pi_conf = ma.DetectionConfidenceLevel(raw_conf).name
                except Exception:  # noqa: BLE001
                    pi_conf = str(raw_conf)
            enf = getattr(pi_settings, "filter_enforcement", None)
            if enf is not None:
                pi_enabled = enf == 1 or str(enf).endswith("ENABLED")

        # RAI Filters
        rai_settings = getattr(fc, "rai_settings", None) if fc else None
        rai_filters_list = []
        if rai_settings and getattr(rai_settings, "rai_filters", None):
            for rf in rai_settings.rai_filters:
                ft = getattr(rf, "filter_type", None)
                cl = getattr(rf, "confidence_level", None)
                try:
                    ft_str = (
                        ma.RaiFilterType(ft).name if ft is not None else "DANGEROUS"
                    )
                except Exception:  # noqa: BLE001
                    ft_str = str(ft)
                try:
                    cl_str = (
                        ma.DetectionConfidenceLevel(cl).name
                        if cl is not None
                        else "MEDIUM_AND_ABOVE"
                    )
                except Exception:  # noqa: BLE001
                    cl_str = str(cl)
                rai_filters_list.append({"type": ft_str, "confidence_level": cl_str})

        # Enforcement type
        enf_type_str = "INSPECT_AND_BLOCK"
        if tm:
            et = getattr(tm, "enforcement_type", None)
            if et is not None:
                try:
                    enf_type_str = ma.Template.TemplateMetadata.EnforcementType(et).name
                except Exception:  # noqa: BLE001
                    enf_type_str = str(et)

        # Multi language detection
        ml_enabled = False
        if tm and getattr(tm, "multi_language_detection", None):
            ml_enabled = bool(
                getattr(
                    tm.multi_language_detection,
                    "enable_multi_language_detection",
                    False,
                )
            )

        # Malicious URI
        uri_settings = (
            getattr(fc, "malicious_uri_filter_settings", None) if fc else None
        )
        uri_enabled = False
        if uri_settings:
            enf = getattr(uri_settings, "filter_enforcement", None)
            uri_enabled = enf == 1 or str(enf).endswith("ENABLED")

        # Basic SDP
        sdp_settings = getattr(fc, "sdp_settings", None) if fc else None
        sdp_enabled = False
        if sdp_settings and getattr(sdp_settings, "basic_config", None):
            enf = getattr(sdp_settings.basic_config, "filter_enforcement", None)
            sdp_enabled = enf == 1 or str(enf).endswith("ENABLED")

        return {
            "pi_and_jailbreak_enabled": pi_enabled,
            "pi_and_jailbreak_confidence": pi_conf,
            "rai_filters": rai_filters_list,
            "enforcement_type": enf_type_str,
            "multi_language_detection": ml_enabled,
            "malicious_uri": uri_enabled,
            "sdp_basic": sdp_enabled,
        }
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_TEMPLATE_CONFIG)


def tune_template(config: dict[str, Any]) -> dict[str, Any]:
    """Update the live Model Armor template with tuned filter settings.

    Args:
        config: Dictionary containing tuning configuration:
            - pi_and_jailbreak_enabled: bool
            - pi_and_jailbreak_confidence: str ("LOW_AND_ABOVE", "MEDIUM_AND_ABOVE", "HIGH")
            - rai_filters: list[dict[str, str]] with "type" and "confidence_level"
            - enforcement_type: str ("INSPECT_AND_BLOCK", "INSPECT_ONLY")
            - multi_language_detection: bool
            - malicious_uri: bool
            - sdp_basic: bool

    Returns:
        Dictionary with "success": bool, "applied_config": dict, and optional "error": str.
    """
    try:
        client = _get_client()
        template_name = _get_template_name()

        # Parse PI confidence
        pi_conf_str = config.get("pi_and_jailbreak_confidence", "LOW_AND_ABOVE")
        pi_conf = getattr(
            ma.DetectionConfidenceLevel,
            pi_conf_str,
            ma.DetectionConfidenceLevel.LOW_AND_ABOVE,
        )

        # Parse PI enforcement
        pi_enabled = config.get("pi_and_jailbreak_enabled", True)
        pi_enf_cls = getattr(
            ma.PiAndJailbreakFilterSettings,
            "FilterEnforcement",
            getattr(
                ma.PiAndJailbreakFilterSettings,
                "PiAndJailbreakFilterEnforcement",
                None,
            ),
        )
        if pi_enf_cls:
            pi_enf_val = getattr(
                pi_enf_cls,
                "ENABLED" if pi_enabled else "DISABLED",
                1 if pi_enabled else 2,
            )
        else:
            pi_enf_val = 1 if pi_enabled else 2

        # Parse RAI filters
        rai_filters_raw = config.get("rai_filters", [])
        parsed_rai_filters = []
        for rf in rai_filters_raw:
            rf_type_str = rf.get("type", "DANGEROUS")
            rf_conf_str = rf.get("confidence_level", "MEDIUM_AND_ABOVE")
            rf_type = getattr(ma.RaiFilterType, rf_type_str, ma.RaiFilterType.DANGEROUS)
            rf_conf = getattr(
                ma.DetectionConfidenceLevel,
                rf_conf_str,
                ma.DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
            )
            parsed_rai_filters.append(
                ma.RaiFilterSettings.RaiFilter(
                    filter_type=rf_type,
                    confidence_level=rf_conf,
                )
            )

        # Parse Malicious URI enforcement
        uri_enabled = config.get("malicious_uri", True)
        uri_enf_cls = getattr(
            ma.MaliciousUriFilterSettings,
            "MaliciousUriFilterEnforcement",
            getattr(ma.MaliciousUriFilterSettings, "FilterEnforcement", None),
        )
        if uri_enf_cls:
            uri_enf_val = getattr(
                uri_enf_cls,
                "ENABLED" if uri_enabled else "DISABLED",
                1 if uri_enabled else 2,
            )
        else:
            uri_enf_val = 1 if uri_enabled else 2

        # Parse Basic SDP enforcement
        sdp_enabled = config.get("sdp_basic", False)
        sdp_enf_cls = getattr(
            ma.SdpBasicConfig,
            "SdpBasicConfigEnforcement",
            getattr(ma.SdpBasicConfig, "FilterEnforcement", None),
        )
        if sdp_enf_cls:
            sdp_enf_val = getattr(
                sdp_enf_cls,
                "ENABLED" if sdp_enabled else "DISABLED",
                1 if sdp_enabled else 2,
            )
        else:
            sdp_enf_val = 1 if sdp_enabled else 2

        filter_config = ma.FilterConfig(
            pi_and_jailbreak_filter_settings=ma.PiAndJailbreakFilterSettings(
                filter_enforcement=pi_enf_val,
                confidence_level=pi_conf,
            ),
            rai_settings=ma.RaiFilterSettings(
                rai_filters=parsed_rai_filters,
            ),
            malicious_uri_filter_settings=ma.MaliciousUriFilterSettings(
                filter_enforcement=uri_enf_val,
            ),
            sdp_settings=ma.SdpFilterSettings(
                basic_config=ma.SdpBasicConfig(
                    filter_enforcement=sdp_enf_val,
                ),
            ),
        )

        # Parse Enforcement Type
        enf_type_str = config.get("enforcement_type", "INSPECT_AND_BLOCK")
        enf_type = getattr(
            ma.Template.TemplateMetadata.EnforcementType,
            enf_type_str,
            ma.Template.TemplateMetadata.EnforcementType.INSPECT_AND_BLOCK,
        )

        # Parse Multi-language detection
        ml_enabled = config.get("multi_language_detection", True)
        ml_detection = ma.Template.TemplateMetadata.MultiLanguageDetection(
            enable_multi_language_detection=ml_enabled,
        )

        template_metadata = ma.Template.TemplateMetadata(
            enforcement_type=enf_type,
            multi_language_detection=ml_detection,
        )

        template = ma.Template(
            name=template_name,
            filter_config=filter_config,
            template_metadata=template_metadata,
        )

        update_mask = FieldMask(paths=["filter_config", "template_metadata"])
        client.update_template(
            request=ma.UpdateTemplateRequest(
                template=template,
                update_mask=update_mask,
            )
        )

        applied = {
            "pi_and_jailbreak_enabled": pi_enabled,
            "pi_and_jailbreak_confidence": pi_conf_str,
            "rai_filters": [
                {
                    "type": rf.get("type", "DANGEROUS"),
                    "confidence_level": rf.get("confidence_level", "MEDIUM_AND_ABOVE"),
                }
                for rf in rai_filters_raw
            ],
            "enforcement_type": enf_type_str,
            "multi_language_detection": ml_enabled,
            "malicious_uri": uri_enabled,
            "sdp_basic": sdp_enabled,
        }

        return {
            "success": True,
            "applied_config": applied,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "applied_config": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
