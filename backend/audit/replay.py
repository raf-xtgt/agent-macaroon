"""Audit reconstruction: query Firestore by chain_id, order by timestamp."""

from datetime import datetime, timezone

from google.cloud import firestore

from audit.trace import Span, _get_firestore_client


def get_chain_spans(chain_id: str) -> list[Span]:
    """Query Firestore `audit_spans` where chain_id == chain_id, ordered by timestamp ascending.

    Args:
        chain_id: The UUID of the delegation chain to query.

    Returns:
        list[Span]: Chronologically ordered list of spans, or an empty list if none found.
    """
    db = _get_firestore_client()
    docs = (
        db.collection("audit_spans")
        .where("chain_id", "==", chain_id)
        .order_by("timestamp", direction=firestore.Query.ASCENDING)
        .stream()
    )

    spans: list[Span] = []
    for doc in docs:
        data = doc.to_dict()
        if not data:
            continue

        raw_ts = data.get("timestamp")
        if isinstance(raw_ts, datetime):
            ts = (
                raw_ts.replace(tzinfo=timezone.utc)
                if raw_ts.tzinfo is None
                else raw_ts.astimezone(timezone.utc)
            )
        elif isinstance(raw_ts, str):
            ts = datetime.fromisoformat(raw_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        span = Span(
            span_id=data.get("span_id", doc.id),
            parent_span_id=data.get("parent_span_id"),
            chain_id=data.get("chain_id"),
            agent_id=data.get("agent_id", "unknown"),
            macaroon_identifier_hash=data.get("macaroon_identifier_hash"),
            action_requested=data.get("action_requested", ""),
            decision=data.get("decision", "deny"),
            reason=data.get("reason", ""),
            timestamp=ts,
            human_subject_id=data.get("human_subject_id"),
            purpose=data.get("purpose"),
        )
        spans.append(span)

    return spans


def derive_verdict(spans: list[Span]) -> str:
    """Return 'blocked' if any span has decision == 'deny', else 'allowed'.

    Args:
        spans: Ordered list of spans for a task chain.

    Returns:
        str: Overall task verdict ("allowed" or "blocked").
    """
    return "blocked" if any(s.decision == "deny" for s in spans) else "allowed"


def hop_count(spans: list[Span]) -> int:
    """Count spans whose action_requested is 'issue_macaroon' or 'transfer_to_agent'.

    Counts delegation hops only — excludes tool-call and screen spans.

    Args:
        spans: Ordered list of spans for a task chain.

    Returns:
        int: Number of delegation hops in the chain.
    """
    return sum(
        1
        for s in spans
        if s.action_requested in ("issue_macaroon", "transfer_to_agent")
    )
