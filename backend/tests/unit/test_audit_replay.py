"""Unit tests for audit replay query layer (F6)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from audit.replay import derive_verdict, get_chain_spans, hop_count
from audit.trace import Span


def test_get_chain_spans_ordered_and_mapped() -> None:
    """Assert get_chain_spans queries Firestore collection with filter/order and returns Span list."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_query_where = MagicMock()
    mock_query_order = MagicMock()

    mock_db.collection.return_value = mock_collection
    mock_collection.where.return_value = mock_query_where
    mock_query_where.order_by.return_value = mock_query_order

    ts1 = datetime(2026, 8, 19, 14, 0, 1, tzinfo=timezone.utc)
    ts2 = datetime(2026, 8, 19, 14, 0, 2, tzinfo=timezone.utc)

    doc1 = MagicMock()
    doc1.id = "s-1"
    doc1.to_dict.return_value = {
        "span_id": "s-1",
        "parent_span_id": None,
        "chain_id": "chain-abc",
        "agent_id": "orchestrator_agent",
        "macaroon_identifier_hash": "h1",
        "action_requested": "issue_macaroon",
        "decision": "allow",
        "reason": "root macaroon issued",
        "timestamp": ts1,
        "human_subject_id": "alice@example.com",
        "purpose": "book travel",
    }

    doc2 = MagicMock()
    doc2.id = "s-2"
    doc2.to_dict.return_value = {
        "span_id": "s-2",
        "parent_span_id": "s-1",
        "chain_id": "chain-abc",
        "agent_id": "researcher_agent",
        "macaroon_identifier_hash": "h2",
        "action_requested": "transfer_to_agent",
        "decision": "allow",
        "reason": "attenuated",
        "timestamp": ts2,
        "human_subject_id": None,
        "purpose": None,
    }

    mock_query_order.stream.return_value = [doc1, doc2]

    with patch("audit.replay._get_firestore_client", return_value=mock_db):
        spans = get_chain_spans("chain-abc")

    assert len(spans) == 2
    assert spans[0].span_id == "s-1"
    assert spans[0].human_subject_id == "alice@example.com"
    assert spans[0].purpose == "book travel"
    assert spans[1].span_id == "s-2"
    assert spans[1].parent_span_id == "s-1"

    mock_db.collection.assert_called_once_with("audit_spans")
    mock_collection.where.assert_called_once_with("chain_id", "==", "chain-abc")


def test_get_chain_spans_empty_returns_empty_list() -> None:
    """Assert non-existent chain returns empty list without raising."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_query_where = MagicMock()
    mock_query_order = MagicMock()

    mock_db.collection.return_value = mock_collection
    mock_collection.where.return_value = mock_query_where
    mock_query_where.order_by.return_value = mock_query_order
    mock_query_order.stream.return_value = []

    with patch("audit.replay._get_firestore_client", return_value=mock_db):
        spans = get_chain_spans("non-existent-chain")

    assert spans == []


def test_derive_verdict() -> None:
    """Assert derive_verdict computes 'allowed' or 'blocked' accurately."""
    ts = datetime.now(timezone.utc)
    s_allow1 = Span("1", None, "c", "a", "h", "issue_macaroon", "allow", "ok", ts)
    s_allow2 = Span("2", "1", "c", "b", "h", "transfer_to_agent", "allow", "ok", ts)
    s_deny = Span("3", "2", "c", "t", "h", "delete_record", "deny", "out of scope", ts)

    assert derive_verdict([s_allow1, s_allow2]) == "allowed"
    assert derive_verdict([s_allow1, s_allow2, s_deny]) == "blocked"


def test_hop_count() -> None:
    """Assert hop_count tallies only issue_macaroon and transfer_to_agent spans."""
    ts = datetime.now(timezone.utc)
    spans = [
        Span("1", None, "c", "orch", "h", "issue_macaroon", "allow", "ok", ts),
        Span("2", "1", "c", "orch", "h", "transfer_to_agent", "allow", "ok", ts),
        Span("3", "2", "c", "res", "h", "transfer_to_agent", "allow", "ok", ts),
        Span("4", "3", "c", "res", "h", "fetch_document", "allow", "ok", ts),
        Span("5", "3", "c", "res", "h", "screen:fetch_document", "allow", "clean", ts),
        Span("6", "3", "c", "tool", "h", "transfer_to_agent", "allow", "ok", ts),
        Span("7", "6", "c", "tool", "h", "read_record", "allow", "ok", ts),
    ]

    # Hops: span 1 (issue), span 2 (transfer), span 3 (transfer), span 6 (transfer) = 4
    assert hop_count(spans) == 4
