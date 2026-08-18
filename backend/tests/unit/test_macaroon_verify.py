"""Unit tests for macaroon signature and caveat verification."""

from datetime import datetime, timedelta, timezone

from macaroon.issue import issue_root_macaroon
from macaroon.verify import (
    CaveatCheckResult,
    VerificationContext,
    verify_caveats,
    verify_macaroon,
    verify_signature,
)


def test_valid_root_macaroon_verifies() -> None:
    """Assert a freshly issued root macaroon verifies against a matching context."""
    root_key = b"super-secret-key-1"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_123",
        purpose="Fetch reports",
        initial_scope={"read", "fetch"},
        root_key=root_key,
        expires_in_minutes=15,
    )

    ctx = VerificationContext(
        requested_action="read",
        presenting_agent_id="orchestrator_agent",
        current_time=now,
    )

    sig_ok = verify_signature(macaroon, root_key)
    assert sig_ok is True

    res = verify_macaroon(macaroon, root_key, ctx)
    assert res.passed is True
    assert res.reason is None


def test_wrong_root_key_fails_signature() -> None:
    """Assert verifying with the wrong root key fails signature verification."""
    root_key = b"correct-key"
    wrong_key = b"wrong-key"
    macaroon = issue_root_macaroon(
        human_subject_id="user_123",
        purpose="Fetch reports",
        initial_scope={"read"},
        root_key=root_key,
    )

    assert verify_signature(macaroon, wrong_key) is False


def test_tampered_caveat_fails_signature_verification() -> None:
    """Proof of security claim: mutating a caveat string directly invalidates HMAC chain."""
    root_key = b"super-secret-key-1"
    macaroon = issue_root_macaroon(
        human_subject_id="user_123",
        purpose="Read only operation",
        initial_scope={"read"},
        root_key=root_key,
    )

    # Attacker attempts in-place mutation of the scope caveat
    tampered = macaroon.copy()
    assert len(tampered.caveats) > 0
    tampered.caveats[0].caveat_id = "scope=delete,read,write"

    # Signature must fail closed
    assert verify_signature(tampered, root_key) is False


def test_stripped_caveat_fails_signature_verification() -> None:
    """Assert stripping a caveat from the chain invalidates the HMAC signature."""
    root_key = b"super-secret-key-1"
    macaroon = issue_root_macaroon(
        human_subject_id="user_123",
        purpose="Read and write",
        initial_scope={"read", "write"},
        root_key=root_key,
    )
    # Add a narrowing caveat
    macaroon.add_first_party_caveat("scope=read")

    # Attacker strips the last caveat to restore write access
    stripped = macaroon.copy()
    stripped.caveats.pop()

    assert verify_signature(stripped, root_key) is False


def test_scope_caveat_violation_reason_formatting() -> None:
    """Assert out-of-scope action fails with exact reason format 'requested=X, allowed=Y'."""
    root_key = b"secret-key"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read tasks",
        initial_scope={"read"},
        root_key=root_key,
    )

    ctx = VerificationContext(
        requested_action="delete",
        presenting_agent_id="orchestrator_agent",
        current_time=now,
    )

    result = verify_caveats(macaroon, ctx)
    assert result.passed is False
    assert result.reason == "scope caveat violated: requested=delete, allowed=read"


def test_agent_caveat_violation() -> None:
    """Assert presenting agent mismatch fails caveat verification."""
    root_key = b"secret-key"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Tool operations",
        initial_scope={"read"},
        root_key=root_key,
    )
    macaroon.add_first_party_caveat("agent=tool_caller_agent")

    ctx = VerificationContext(
        requested_action="read",
        presenting_agent_id="rogue_agent",
        current_time=now,
    )

    result = verify_caveats(macaroon, ctx)
    assert result.passed is False
    assert (
        result.reason
        == "agent caveat violated: presenting=rogue_agent, expected=tool_caller_agent"
    )


def test_expired_macaroon_fails() -> None:
    """Assert checking an expired macaroon fails caveat verification."""
    root_key = b"secret-key"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Time sensitive task",
        initial_scope={"read"},
        root_key=root_key,
        expires_in_minutes=5,
    )

    # Simulate verification 10 minutes in the future
    future_time = now + timedelta(minutes=10)
    ctx = VerificationContext(
        requested_action="read",
        presenting_agent_id="orchestrator_agent",
        current_time=future_time,
    )

    result = verify_caveats(macaroon, ctx)
    assert result.passed is False
    assert result.reason is not None
    assert "macaroon expired:" in result.reason


def test_structural_widening_fails_caveat_verification() -> None:
    """Assert that a caveat chain attempting to widen scope fails structural check."""
    root_key = b"secret-key"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )
    # Illegitimate widening caveat added
    macaroon.add_first_party_caveat("scope=read,write")

    ctx = VerificationContext(
        requested_action="read",
        presenting_agent_id="orchestrator_agent",
        current_time=now,
    )

    result = verify_caveats(macaroon, ctx)
    assert result.passed is False
    assert (
        result.reason == "structural narrowing violation: scope widened across caveats"
    )


def test_verify_macaroon_short_circuits_on_bad_signature() -> None:
    """Assert verify_macaroon short-circuits if signature is invalid."""
    root_key = b"secret-key"
    wrong_key = b"wrong-key"
    now = datetime.now(timezone.utc)
    macaroon = issue_root_macaroon(
        human_subject_id="user_alice",
        purpose="Read task",
        initial_scope={"read"},
        root_key=root_key,
    )

    ctx = VerificationContext(
        requested_action="read",
        presenting_agent_id="orchestrator_agent",
        current_time=now,
    )

    result: CaveatCheckResult = verify_macaroon(macaroon, wrong_key, ctx)
    assert result.passed is False
    assert "signature verification failed" in (result.reason or "")
