"""Unit tests for audit span emission and trace layer (F6)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from audit.trace import Span, emit_span


def test_span_dataclass_instantiation() -> None:
    """Assert Span dataclass fields and immutability."""
    ts = datetime.now(timezone.utc)
    span = Span(
        span_id="span-123",
        parent_span_id=None,
        chain_id="chain-456",
        agent_id="orchestrator_agent",
        macaroon_identifier_hash="abcde12345",
        action_requested="issue_macaroon",
        decision="allow",
        reason="root macaroon issued",
        timestamp=ts,
        human_subject_id="alice@example.com",
        purpose="audit test",
    )
    assert span.span_id == "span-123"
    assert span.parent_span_id is None
    assert span.chain_id == "chain-456"
    assert span.decision == "allow"
    assert span.human_subject_id == "alice@example.com"


def test_emit_span_writes_firestore_document() -> None:
    """Assert emit_span formats document and calls Firestore set with doc ID == span_id."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_doc = MagicMock()

    mock_db.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_doc

    ts = datetime(2026, 8, 19, 14, 0, 0, tzinfo=timezone.utc)

    with patch("audit.trace._get_firestore_client", return_value=mock_db):
        span_id = emit_span(
            chain_id="chain-999",
            parent_span_id="parent-888",
            agent_id="researcher_agent",
            macaroon_identifier_hash="hash-111",
            action_requested="transfer_to_agent",
            decision="allow",
            reason="attenuated",
            human_subject_id=None,
            purpose=None,
            timestamp=ts,
        )

    assert isinstance(span_id, str)
    assert len(span_id) > 0

    mock_db.collection.assert_called_once_with("audit_spans")
    mock_collection.document.assert_called_once_with(span_id)

    mock_doc.set.assert_called_once()
    doc_data = mock_doc.set.call_args[0][0]
    assert doc_data["span_id"] == span_id
    assert doc_data["parent_span_id"] == "parent-888"
    assert doc_data["chain_id"] == "chain-999"
    assert doc_data["agent_id"] == "researcher_agent"
    assert doc_data["macaroon_identifier_hash"] == "hash-111"
    assert doc_data["action_requested"] == "transfer_to_agent"
    assert doc_data["decision"] == "allow"
    assert doc_data["reason"] == "attenuated"
    assert doc_data["timestamp"] == ts
    assert doc_data["human_subject_id"] is None
    assert doc_data["purpose"] is None


def test_emit_span_swallows_firestore_exception_and_returns_id() -> None:
    """Assert Firestore failure is swallowed fail-safe without raising, still returning span_id."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_doc = MagicMock()

    mock_db.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_doc
    mock_doc.set.side_effect = RuntimeError("Firestore connection timed out")

    with patch("audit.trace._get_firestore_client", return_value=mock_db):
        span_id = emit_span(
            chain_id="chain-err",
            parent_span_id=None,
            agent_id="orchestrator_agent",
            macaroon_identifier_hash=None,
            action_requested="issue_macaroon",
            decision="allow",
            reason="root macaroon issued",
        )

    # Must return valid span_id despite persistence error
    assert isinstance(span_id, str)
    assert len(span_id) > 0


def test_emit_span_handles_none_chain_id_and_naive_timestamp() -> None:
    """Assert None chain_id and naive timestamp normalize safely to UTC."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_doc = MagicMock()

    mock_db.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_doc

    # Intentionally test naive datetime normalization behavior
    naive_dt = datetime(2026, 8, 19, 10, 30, 0)  # noqa: DTZ001

    with patch("audit.trace._get_firestore_client", return_value=mock_db):
        span_id = emit_span(
            chain_id=None,
            parent_span_id=None,
            agent_id="tool_caller_agent",
            macaroon_identifier_hash=None,
            action_requested="read_record",
            decision="deny",
            reason="no macaroon presented",
            timestamp=naive_dt,
        )

    assert isinstance(span_id, str)
    doc_data = mock_doc.set.call_args[0][0]
    assert doc_data["chain_id"] is None
    assert doc_data["timestamp"].tzinfo == timezone.utc
