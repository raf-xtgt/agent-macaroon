"""Cryptographic signature and caveat verification for macaroons."""

from dataclasses import dataclass
from datetime import datetime, timezone

from pymacaroons import Macaroon, Verifier
from pymacaroons.exceptions import (
    MacaroonException,
    MacaroonInvalidSignatureException,
    MacaroonVerificationFailedException,
)


@dataclass(frozen=True)
class VerificationContext:
    """Context information against which a macaroon's caveats are evaluated.

    Attributes:
        requested_action: The action verb the agent is attempting (e.g. 'read', 'delete').
        presenting_agent_id: The ID of the agent presenting the macaroon.
        current_time: The current timestamp against which to check expiry.
    """

    requested_action: str
    presenting_agent_id: str
    current_time: datetime


@dataclass(frozen=True)
class CaveatCheckResult:
    """Result of a macaroon verification check.

    Attributes:
        passed: True if signature and all caveats were satisfied, False otherwise.
        reason: Explanatory failure reason on failure, or None on success.
    """

    passed: bool
    reason: str | None = None


def verify_signature(macaroon: Macaroon, root_key: bytes) -> bool:
    """Verify the HMAC signature chain of a macaroon using the root key.

    Replays HMAC computation across all first-party caveats using pymacaroons.Verifier.
    Returns False on any signature mismatch or tampered caveat without raising.

    Args:
        macaroon: Macaroon bearer token to verify.
        root_key: Secret root HMAC key.

    Returns:
        bool: True if cryptographic signature chain is valid, False otherwise.
    """
    verifier = Verifier()
    # Satisfy all first-party caveats in the verifier's loop to compute the complete HMAC chain
    verifier.satisfy_general(lambda _: True)
    try:
        return verifier.verify(macaroon, root_key)
    except (
        MacaroonInvalidSignatureException,
        MacaroonVerificationFailedException,
        MacaroonException,
        ValueError,
        TypeError,
    ):
        return False


def _parse_scope_predicate(predicate: str) -> set[str]:
    """Parse a 'scope=...' caveat predicate into a set of action strings."""
    actions_raw = predicate.removeprefix("scope=").strip()
    if not actions_raw:
        return set()
    return {action.strip() for action in actions_raw.split(",") if action.strip()}


def _normalize_datetime(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_caveats(
    macaroon: Macaroon, context: VerificationContext
) -> CaveatCheckResult:
    """Evaluate all first-party caveats against a verification context.

    Enforces:
    1. Structural narrowing: Each scope caveat must be a subset of the previous scope.
    2. Expiration: Current time must not exceed the expires< timestamp.
    3. Presenting agent: Must match the last agent= caveat (if any agent caveat exists).
    4. Delegation depth: Remaining max_depth must be non-negative.
    5. Action scope: requested_action must be present in the last scope= caveat.

    Args:
        macaroon: Macaroon bearer token.
        context: Context of the current execution request.

    Returns:
        CaveatCheckResult: Outcome with detailed reason on failure.
    """
    scopes: list[set[str]] = []
    last_agent: str | None = None
    expires_at: datetime | None = None
    last_depth: int | None = None

    for caveat in macaroon.first_party_caveats():
        cid = (
            caveat.caveat_id
            if isinstance(caveat.caveat_id, str)
            else caveat.caveat_id.decode("utf-8")
        )

        if cid.startswith("scope="):
            parsed_scope = _parse_scope_predicate(cid)
            scopes.append(parsed_scope)
        elif cid.startswith("agent="):
            last_agent = cid.removeprefix("agent=").strip()
        elif cid.startswith("expires<"):
            try:
                raw_ts = cid.removeprefix("expires<").strip()
                expires_at = _normalize_datetime(datetime.fromisoformat(raw_ts))
            except (ValueError, TypeError):
                return CaveatCheckResult(
                    passed=False,
                    reason=f"invalid expiration caveat timestamp format: {cid}",
                )
        elif cid.startswith("max_depth<="):
            try:
                raw_depth = cid.removeprefix("max_depth<=").strip()
                last_depth = int(raw_depth)
            except (ValueError, TypeError):
                return CaveatCheckResult(
                    passed=False,
                    reason=f"invalid max_depth caveat format: {cid}",
                )

    # 1. Structural narrowing check
    for i in range(1, len(scopes)):
        if not scopes[i].issubset(scopes[i - 1]):
            return CaveatCheckResult(
                passed=False,
                reason="structural narrowing violation: scope widened across caveats",
            )

    # 2. Expiration check
    if expires_at is not None:
        current_time_norm = _normalize_datetime(context.current_time)
        if current_time_norm >= expires_at:
            return CaveatCheckResult(
                passed=False,
                reason=(
                    f"macaroon expired: expired_at={expires_at.isoformat()}, "
                    f"current_time={current_time_norm.isoformat()}"
                ),
            )

    # 3. Agent binding check
    # Note: If no agent= caveat exists, the macaroon is at the root level and not yet restricted to an agent.
    if last_agent is not None and context.presenting_agent_id.strip() != last_agent:
        return CaveatCheckResult(
            passed=False,
            reason=(
                f"agent caveat violated: presenting={context.presenting_agent_id}, "
                f"expected={last_agent}"
            ),
        )

    # 4. Delegation depth check
    if last_depth is not None and last_depth < 0:
        return CaveatCheckResult(
            passed=False,
            reason="delegation depth exhausted",
        )

    # 5. Scope action check
    if not scopes:
        return CaveatCheckResult(
            passed=False,
            reason="scope caveat missing: no actions allowed",
        )

    effective_scope = scopes[-1]
    if context.requested_action not in effective_scope:
        allowed_str = ",".join(sorted(effective_scope))
        return CaveatCheckResult(
            passed=False,
            reason=(
                f"scope caveat violated: requested={context.requested_action}, "
                f"allowed={allowed_str}"
            ),
        )

    return CaveatCheckResult(passed=True, reason=None)


def verify_macaroon(
    macaroon: Macaroon, root_key: bytes, context: VerificationContext
) -> CaveatCheckResult:
    """Verify both signature and caveats of a presented macaroon.

    Fails closed: if the signature check fails, verification short-circuits
    immediately with passed=False without checking caveats.

    Args:
        macaroon: Macaroon bearer token.
        root_key: Secret root HMAC key.
        context: Context of the current execution request.

    Returns:
        CaveatCheckResult: Overall verification result.
    """
    if not verify_signature(macaroon, root_key):
        return CaveatCheckResult(
            passed=False,
            reason="signature verification failed: invalid signature or tampered caveats",
        )
    return verify_caveats(macaroon, context)
