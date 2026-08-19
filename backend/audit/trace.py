"""Structured, chain-ID-linked audit logging and span emission."""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

_firestore_client: firestore.Client | None = None


def _get_firestore_client() -> firestore.Client:
    """Retrieve or lazily initialize the singleton Firestore client."""
    global _firestore_client
    if _firestore_client is None:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        _firestore_client = firestore.Client(project=project)
    return _firestore_client


@dataclass(frozen=True)
class Span:
    """Immutable record of an audit span representing a delegation or gateway event.

    Strictly omits raw HMAC keys and signatures, storing cryptographic identifier
    hashes and caveat metadata for non-repudiable forensic reconstruction (F6).
    """

    span_id: str
    parent_span_id: str | None
    chain_id: str | None
    agent_id: str
    macaroon_identifier_hash: str | None
    action_requested: str
    decision: str  # "allow" | "deny"
    reason: str
    timestamp: datetime
    human_subject_id: str | None = None  # root span only
    purpose: str | None = None  # root span only


def emit_span(
    chain_id: str | None,
    parent_span_id: str | None,
    agent_id: str,
    macaroon_identifier_hash: str | None,
    action_requested: str,
    decision: str,
    reason: str,
    human_subject_id: str | None = None,
    purpose: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    """Write one span to Firestore collection `audit_spans`, doc ID = generated span_id.

    Returns the generated span_id (caller needs it to set as parent_span_id on the next hop).

    This is an audit emission path, not a security-decision path: any Firestore write failure
    is safely swallowed to ensure that audit persistence issues never alter or break
    an authorization decision already rendered by the gateway.
    """
    span_id = str(uuid.uuid4())

    if timestamp is None:
        ts = datetime.now(timezone.utc)
    elif timestamp.tzinfo is None:
        ts = timestamp.replace(tzinfo=timezone.utc)
    else:
        ts = timestamp.astimezone(timezone.utc)

    span_doc: dict[str, Any] = {
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "chain_id": chain_id,
        "agent_id": agent_id,
        "macaroon_identifier_hash": macaroon_identifier_hash,
        "action_requested": action_requested,
        "decision": decision,
        "reason": reason,
        "timestamp": ts,
        "human_subject_id": human_subject_id,
        "purpose": purpose,
    }

    try:
        db = _get_firestore_client()
        db.collection("audit_spans").document(span_id).set(span_doc)
    except Exception:  # noqa: BLE001, S110
        # Audit emission path is fail-safe: write failures must not alter or break
        # authorization decisions already rendered by the gateway. The generated span_id
        # is still returned so downstream callers can maintain parent-span pointers.
        pass

    return span_id
