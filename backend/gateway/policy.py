"""Framework-agnostic fail-closed policy decision point.

Performs signature verification, first-party caveat evaluation, and live Agent
Registry scope ceiling enforcement. Default denies on any failure or exception.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from pymacaroons import Macaroon

from macaroon.issue import parse_identifier
from macaroon.verify import VerificationContext, verify_macaroon
from registry.agents_registry import AgentRegistry


@dataclass(frozen=True)
class GatewayDecision:
    """Immutable result of a gateway policy evaluation.

    Contains all forensic fields needed by downstream audit (F6) and memory (F7)
    layers, strictly omitting any secret key material or raw cryptographic signatures.

    Attributes:
        allowed: True if the request is fully authorized, False otherwise.
        reason: Explanatory text for the decision.
        requested_action: Action verb requested by the presenting agent.
        presenting_agent_id: Identifier of the agent presenting the token.
        macaroon_identifier_hash: SHA-256 hex digest of the macaroon's identifier string,
            or None if no macaroon was presented or identifier could not be hashed.
        chain_id: Delegation chain UUID extracted from the identifier, or None.
        timestamp: Timestamp of the evaluation in UTC.
    """

    allowed: bool
    reason: str
    requested_action: str
    presenting_agent_id: str
    macaroon_identifier_hash: str | None
    chain_id: str | None
    timestamp: datetime


def _normalize_datetime(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate(
    macaroon: Macaroon | None,
    requested_action: str,
    presenting_agent_id: str,
    root_key: bytes,
    registry: AgentRegistry,
    current_time: datetime | None = None,
) -> GatewayDecision:
    """Evaluate whether an agent is authorized to execute a requested action.

    Performs three enforcement steps in order:
    1. Signature and caveat verification via verify_macaroon.
    2. Live Agent Registry ceiling check for the presenting agent.
    3. Fail-closed default deny on any parsing, verification, or unexpected exception.

    Args:
        macaroon: Macaroon bearer token presented by the agent, or None.
        requested_action: Action verb being attempted (e.g., 'read', 'delete').
        presenting_agent_id: Identifier of the agent executing the action.
        root_key: Secret root HMAC key for signature validation.
        registry: AgentRegistry instance for live scope ceiling lookups.
        current_time: Evaluation timestamp (defaults to current UTC time).

    Returns:
        GatewayDecision: Comprehensive decision object detailing allow/deny and reason.
    """
    ts = (
        _normalize_datetime(current_time)
        if current_time is not None
        else datetime.now(timezone.utc)
    )

    identifier_hash: str | None = None
    chain_id: str | None = None

    try:
        # Step 0: Check presence of bearer token
        if macaroon is None:
            return GatewayDecision(
                allowed=False,
                reason="no macaroon presented",
                requested_action=requested_action,
                presenting_agent_id=presenting_agent_id,
                macaroon_identifier_hash=None,
                chain_id=None,
                timestamp=ts,
            )

        # Extract identifier hash and chain ID for audit linkage (never storing secret keys)
        try:
            raw_id = macaroon.identifier
            raw_id_bytes = raw_id.encode("utf-8") if isinstance(raw_id, str) else raw_id
            identifier_hash = hashlib.sha256(raw_id_bytes).hexdigest()
        except (AttributeError, UnicodeError, TypeError):
            identifier_hash = None

        try:
            parsed_id = parse_identifier(macaroon)
            if isinstance(parsed_id, dict):
                chain_id = parsed_id.get("chain_id")
        except (
            json.JSONDecodeError,
            TypeError,
            AttributeError,
            KeyError,
            UnicodeError,
        ):
            chain_id = None

        # Step 1: Signature + caveat verification
        context = VerificationContext(
            requested_action=requested_action,
            presenting_agent_id=presenting_agent_id,
            current_time=ts,
        )
        verification_result = verify_macaroon(macaroon, root_key, context)
        if not verification_result.passed:
            return GatewayDecision(
                allowed=False,
                reason=verification_result.reason
                or "signature/caveat verification failed",
                requested_action=requested_action,
                presenting_agent_id=presenting_agent_id,
                macaroon_identifier_hash=identifier_hash,
                chain_id=chain_id,
                timestamp=ts,
            )

        # Step 2: Live registry ceiling backstop
        agent_ceiling = registry.ceiling(presenting_agent_id)
        if requested_action not in agent_ceiling:
            ceiling_str = ",".join(sorted(agent_ceiling))
            return GatewayDecision(
                allowed=False,
                reason=(
                    f"agent registry ceiling exceeded: requested={requested_action}, "
                    f"allowed_by_ceiling={ceiling_str}"
                ),
                requested_action=requested_action,
                presenting_agent_id=presenting_agent_id,
                macaroon_identifier_hash=identifier_hash,
                chain_id=chain_id,
                timestamp=ts,
            )

        # All checks passed
        return GatewayDecision(
            allowed=True,
            reason="allowed",
            requested_action=requested_action,
            presenting_agent_id=presenting_agent_id,
            macaroon_identifier_hash=identifier_hash,
            chain_id=chain_id,
            timestamp=ts,
        )

    except Exception as exc:  # noqa: BLE001
        # Step 3: Default deny — fail closed, always (AGENTS.md non-negotiable rule).
        # Catches any unexpected exception (e.g. malformed macaroon data structure,
        # registry failure, etc.) to guarantee that errors never allow unverified actions.
        return GatewayDecision(
            allowed=False,
            reason=f"gateway evaluation error (fail-closed): {exc}",
            requested_action=requested_action,
            presenting_agent_id=presenting_agent_id,
            macaroon_identifier_hash=identifier_hash,
            chain_id=chain_id,
            timestamp=ts,
        )
