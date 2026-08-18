"""Unit tests for root macaroon issuance (F1)."""

import uuid
from datetime import datetime

from macaroon.issue import issue_root_macaroon, parse_identifier


def test_issue_root_macaroon_identifier_roundtrip() -> None:
    """Assert minted macaroon parses identifier fields correctly."""
    root_key = b"super-secret-root-key"
    human_id = "user_alice@enterprise.com"
    purpose = "Retrieve and summarize Q3 audit records"
    scope = {"read", "fetch"}

    macaroon = issue_root_macaroon(
        human_subject_id=human_id,
        purpose=purpose,
        initial_scope=scope,
        root_key=root_key,
    )

    parsed = parse_identifier(macaroon)
    assert parsed["human_subject_id"] == human_id
    assert parsed["purpose"] == purpose
    assert "chain_id" in parsed
    # Verify chain_id is valid UUID
    uuid_obj = uuid.UUID(parsed["chain_id"])
    assert str(uuid_obj) == parsed["chain_id"]
    assert "issued_at" in parsed
    # Verify issued_at is valid ISO timestamp
    issued_dt = datetime.fromisoformat(parsed["issued_at"])
    assert issued_dt is not None


def test_issue_root_macaroon_explicit_chain_id() -> None:
    """Assert explicitly supplied chain_id is preserved."""
    root_key = b"super-secret-root-key"
    explicit_chain_id = str(uuid.uuid4())

    macaroon = issue_root_macaroon(
        human_subject_id="user_bob",
        purpose="Run reports",
        initial_scope={"read"},
        root_key=root_key,
        chain_id=explicit_chain_id,
    )

    parsed = parse_identifier(macaroon)
    assert parsed["chain_id"] == explicit_chain_id


def test_issue_root_macaroon_initial_caveats() -> None:
    """Assert initial caveats (scope, expires<, max_depth<=) are present and formatted."""
    root_key = b"super-secret-root-key"
    initial_scope = {"write", "read", "delete"}

    macaroon = issue_root_macaroon(
        human_subject_id="user_admin",
        purpose="Perform maintenance",
        initial_scope=initial_scope,
        root_key=root_key,
        expires_in_minutes=20,
        max_depth=4,
    )

    caveat_ids = [c.caveat_id for c in macaroon.first_party_caveats()]
    assert len(caveat_ids) == 3

    # 1. scope caveat (sorted actions)
    assert caveat_ids[0] == "scope=delete,read,write"

    # 2. expires< caveat
    assert caveat_ids[1].startswith("expires<")
    expires_ts = caveat_ids[1].removeprefix("expires<")
    expires_dt = datetime.fromisoformat(expires_ts)
    assert expires_dt is not None

    # 3. max_depth<= caveat
    assert caveat_ids[2] == "max_depth<=4"

    # Ensure no agent= caveat exists at root
    assert not any(c.startswith("agent=") for c in caveat_ids)
