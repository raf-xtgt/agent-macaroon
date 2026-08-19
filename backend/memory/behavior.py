"""Cross-session violation-history records (Firestore-backed)."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud.firestore import FieldFilter

from audit.trace import _get_firestore_client


@dataclass(frozen=True)
class ViolationRecord:
    """Immutable record of an authorization denial stored in Memory Bank.

    Scoped per-agent in Firestore subcollections to provide compact cross-session
    behavioral summaries without logging sensitive key material.
    """

    agent_id: str
    chain_id: str | None
    outcome: str  # "denied" — MVP only writes denials; "allowed" reserved for schema extension
    reason: str
    timestamp: datetime


def record_denial(
    agent_id: str,
    chain_id: str | None,
    reason: str,
    timestamp: datetime | None = None,
) -> None:
    """Write one denial record to Firestore `agent_memory/{agent_id}/records/{record_id}`.

    This write path is fail-safe: write failures must not alter or break authorization
    decisions already rendered by the gateway.
    """
    record_id = str(uuid.uuid4())

    if timestamp is None:
        ts = datetime.now(timezone.utc)
    elif timestamp.tzinfo is None:
        ts = timestamp.replace(tzinfo=timezone.utc)
    else:
        ts = timestamp.astimezone(timezone.utc)

    record_doc: dict[str, Any] = {
        "record_id": record_id,
        "agent_id": agent_id,
        "chain_id": chain_id,
        "outcome": "denied",
        "reason": reason,
        "timestamp": ts,
    }

    try:
        db = _get_firestore_client()
        (
            db.collection("agent_memory")
            .document(agent_id)
            .collection("records")
            .document(record_id)
            .set(record_doc)
        )
    except Exception:  # noqa: BLE001, S110
        # Memory Bank write failure is fail-safe: persistence errors must never
        # crash or alter gateway evaluation results.
        pass


def recent_violation_count(
    agent_id: str,
    window: timedelta = timedelta(hours=24),
) -> int:
    """Count denial records for agent_id with timestamp >= now - window.

    Fail-closed to 0 on any exception. Per AGENTS.md: "Memory Bank never overrides
    caveats" — Memory Bank only provides an advisory flag alongside cryptographic
    decisions, so the safe failure mode on query error is to under-report (0 violations)
    rather than block or alter authorization flow.
    """
    cutoff = datetime.now(timezone.utc) - window
    count = 0

    try:
        db = _get_firestore_client()
        docs = (
            db.collection("agent_memory")
            .document(agent_id)
            .collection("records")
            .where(filter=FieldFilter("timestamp", ">=", cutoff))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict()
            if not data:
                continue
            if data.get("outcome") == "denied":
                raw_ts = data.get("timestamp")
                if isinstance(raw_ts, datetime):
                    ts_utc = (
                        raw_ts.replace(tzinfo=timezone.utc)
                        if raw_ts.tzinfo is None
                        else raw_ts.astimezone(timezone.utc)
                    )
                    if ts_utc >= cutoff:
                        count += 1
                elif isinstance(raw_ts, str):
                    try:
                        ts_dt = datetime.fromisoformat(raw_ts)
                        ts_utc = (
                            ts_dt.replace(tzinfo=timezone.utc)
                            if ts_dt.tzinfo is None
                            else ts_dt.astimezone(timezone.utc)
                        )
                        if ts_utc >= cutoff:
                            count += 1
                    except ValueError:
                        count += 1
                else:
                    count += 1
        return count
    except Exception:  # noqa: BLE001
        # Memory Bank never overrides caveats: fail closed to 0 violations on read error
        return 0
