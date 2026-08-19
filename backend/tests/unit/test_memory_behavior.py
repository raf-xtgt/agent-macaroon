"""Unit tests for the Memory Bank cross-session behavioral memory layer (F7)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from memory.behavior import ViolationRecord, recent_violation_count, record_denial


def test_violation_record_dataclass_instantiation() -> None:
    """Assert ViolationRecord dataclass fields and immutability."""
    ts = datetime.now(timezone.utc)
    record = ViolationRecord(
        agent_id="tool_caller_agent",
        chain_id="chain-xyz-123",
        outcome="denied",
        reason="scope caveat violated: requested=delete, allowed=read",
        timestamp=ts,
    )
    assert record.agent_id == "tool_caller_agent"
    assert record.chain_id == "chain-xyz-123"
    assert record.outcome == "denied"
    assert record.reason == "scope caveat violated: requested=delete, allowed=read"
    assert record.timestamp == ts

    with pytest.raises(AttributeError):
        record.outcome = "allowed"  # type: ignore[misc]


def test_record_denial_writes_firestore_subcollection_document() -> None:
    """Assert record_denial writes to agent_memory/{agent_id}/records/{record_id}."""
    mock_db = MagicMock()
    mock_agent_doc = MagicMock()
    mock_records_col = MagicMock()
    mock_record_doc = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_agent_doc
    mock_agent_doc.collection.return_value = mock_records_col
    mock_records_col.document.return_value = mock_record_doc

    ts = datetime(2026, 8, 19, 14, 0, 0, tzinfo=timezone.utc)

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        record_denial(
            agent_id="tool_caller_agent",
            chain_id="chain-456",
            reason="out of scope tool call",
            timestamp=ts,
        )

    mock_db.collection.assert_called_once_with("agent_memory")
    mock_db.collection.return_value.document.assert_called_once_with(
        "tool_caller_agent"
    )
    mock_agent_doc.collection.assert_called_once_with("records")
    mock_records_col.document.assert_called_once()
    mock_record_doc.set.assert_called_once()

    doc_data = mock_record_doc.set.call_args[0][0]
    assert doc_data["agent_id"] == "tool_caller_agent"
    assert doc_data["chain_id"] == "chain-456"
    assert doc_data["outcome"] == "denied"
    assert doc_data["reason"] == "out of scope tool call"
    assert doc_data["timestamp"] == ts
    assert isinstance(doc_data["record_id"], str)
    assert len(doc_data["record_id"]) > 0


def test_record_denial_swallows_firestore_exception() -> None:
    """Assert record_denial swallows persistence exceptions fail-safe."""
    mock_db = MagicMock()
    mock_agent_doc = MagicMock()
    mock_records_col = MagicMock()
    mock_record_doc = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_agent_doc
    mock_agent_doc.collection.return_value = mock_records_col
    mock_records_col.document.return_value = mock_record_doc
    mock_record_doc.set.side_effect = RuntimeError("Firestore unavailable")

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        # Must not raise
        record_denial(
            agent_id="researcher_agent",
            chain_id="chain-fail",
            reason="attenuation depth exceeded",
        )


def test_record_denial_handles_naive_and_none_timestamp() -> None:
    """Assert record_denial handles naive datetime and None timestamp normalizing to UTC."""
    mock_db = MagicMock()
    mock_agent_doc = MagicMock()
    mock_records_col = MagicMock()
    mock_record_doc = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_agent_doc
    mock_agent_doc.collection.return_value = mock_records_col
    mock_records_col.document.return_value = mock_record_doc

    naive_dt = datetime(2026, 8, 19, 10, 30, 0)  # noqa: DTZ001

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        record_denial(
            agent_id="tool_caller_agent",
            chain_id=None,
            reason="denied",
            timestamp=naive_dt,
        )

    doc_data = mock_record_doc.set.call_args[0][0]
    assert doc_data["chain_id"] is None
    assert doc_data["timestamp"].tzinfo == timezone.utc


def test_recent_violation_count_within_window_and_excludes_outside() -> None:
    """Assert recent_violation_count tallies denials within window and ignores older or allowed records."""
    mock_db = MagicMock()
    mock_agent_doc = MagicMock()
    mock_records_col = MagicMock()
    mock_query_where = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_agent_doc
    mock_agent_doc.collection.return_value = mock_records_col
    mock_records_col.where.return_value = mock_query_where

    now = datetime.now(timezone.utc)
    ts_in1 = now - timedelta(hours=1)
    ts_in2 = now - timedelta(hours=5)
    ts_out = now - timedelta(hours=48)
    ts_allowed = now - timedelta(hours=2)

    doc1 = MagicMock()
    doc1.to_dict.return_value = {
        "record_id": "r1",
        "agent_id": "agent_x",
        "outcome": "denied",
        "reason": "r1",
        "timestamp": ts_in1,
    }

    doc2 = MagicMock()
    doc2.to_dict.return_value = {
        "record_id": "r2",
        "agent_id": "agent_x",
        "outcome": "denied",
        "reason": "r2",
        "timestamp": ts_in2,
    }

    # doc3 is older than the 24h window (simulating potential query boundary or mock feed)
    doc3 = MagicMock()
    doc3.to_dict.return_value = {
        "record_id": "r3",
        "agent_id": "agent_x",
        "outcome": "denied",
        "reason": "r3",
        "timestamp": ts_out,
    }

    # doc4 is an allowed record (schema extension reserve)
    doc4 = MagicMock()
    doc4.to_dict.return_value = {
        "record_id": "r4",
        "agent_id": "agent_x",
        "outcome": "allowed",
        "reason": "",
        "timestamp": ts_allowed,
    }

    mock_query_where.stream.return_value = [doc1, doc2, doc3, doc4]

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        count = recent_violation_count("agent_x", window=timedelta(hours=24))

    assert count == 2
    mock_db.collection.assert_called_once_with("agent_memory")
    mock_db.collection.return_value.document.assert_called_once_with("agent_x")
    mock_agent_doc.collection.assert_called_once_with("records")
    mock_records_col.where.assert_called_once()
    _, kwargs = mock_records_col.where.call_args
    filter_arg = kwargs.get("filter")
    assert filter_arg is not None
    assert filter_arg.field_path == "timestamp"
    assert filter_arg.op_string == ">="


def test_recent_violation_count_fails_closed_to_zero_on_exception() -> None:
    """Assert query errors fail closed to 0 violations to uphold non-override guarantee."""
    mock_db = MagicMock()
    mock_db.collection.side_effect = RuntimeError("Firestore query failed")

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        count = recent_violation_count("agent_y")

    assert count == 0


def test_recent_violation_count_handles_iso_string_and_empty_docs() -> None:
    """Assert recent_violation_count parses string timestamps and handles empty docs gracefully."""
    mock_db = MagicMock()
    mock_agent_doc = MagicMock()
    mock_records_col = MagicMock()
    mock_query_where = MagicMock()

    mock_db.collection.return_value.document.return_value = mock_agent_doc
    mock_agent_doc.collection.return_value = mock_records_col
    mock_records_col.where.return_value = mock_query_where

    now = datetime.now(timezone.utc)
    iso_ts = (now - timedelta(minutes=30)).isoformat()

    doc_str = MagicMock()
    doc_str.to_dict.return_value = {
        "outcome": "denied",
        "timestamp": iso_ts,
    }

    doc_empty = MagicMock()
    doc_empty.to_dict.return_value = {}

    doc_invalid_ts = MagicMock()
    doc_invalid_ts.to_dict.return_value = {
        "outcome": "denied",
        "timestamp": "not-a-timestamp",
    }

    mock_query_where.stream.return_value = [doc_str, doc_empty, doc_invalid_ts]

    with patch("memory.behavior._get_firestore_client", return_value=mock_db):
        count = recent_violation_count("agent_z", window=timedelta(hours=1))

    # doc_str is valid and inside window (+1), doc_empty is ignored (+0), doc_invalid_ts falls back (+1)
    assert count == 2
