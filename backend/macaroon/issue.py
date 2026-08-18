"""Root macaroon minting with human delegation provenance (HDP) metadata."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pymacaroons import Macaroon


def issue_root_macaroon(
    human_subject_id: str,
    purpose: str,
    initial_scope: set[str],
    root_key: bytes,
    chain_id: str | None = None,
    location: str = "agent-macaroon://orchestrator",
    expires_in_minutes: int = 15,
    max_depth: int = 5,
) -> Macaroon:
    """Mint the root macaroon for a task delegation chain.

    Binds human subject provenance, task purpose, chain ID, and timestamp into the
    macaroon's structured JSON identifier. Appends initial first-party caveats for
    scope, expiry, and max delegation depth.

    Args:
        human_subject_id: Identifier of the human who initiated the task.
        purpose: Free-text description of the task purpose.
        initial_scope: Set of action verbs granted to the root task.
        root_key: Secret HMAC key material for signing the root macaroon.
        chain_id: UUID shared across the entire delegation chain. Generated if omitted.
        location: Identifier of the issuing authority / entry agent.
        expires_in_minutes: Time-to-live in minutes (default 15).
        max_depth: Maximum delegation hops permitted (default 5).

    Returns:
        Macaroon: The minted and cryptographically signed root macaroon.
    """
    if chain_id is None:
        chain_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    issued_at_iso = now.isoformat()
    expires_at_iso = (now + timedelta(minutes=expires_in_minutes)).isoformat()

    identifier_dict = {
        "human_subject_id": human_subject_id,
        "purpose": purpose,
        "chain_id": chain_id,
        "issued_at": issued_at_iso,
    }
    identifier_json = json.dumps(identifier_dict, separators=(",", ":"), sort_keys=True)

    macaroon = Macaroon(
        location=location,
        identifier=identifier_json,
        key=root_key,
    )

    # Append initial first-party caveats
    scope_str = ",".join(sorted(initial_scope))
    macaroon.add_first_party_caveat(f"scope={scope_str}")
    macaroon.add_first_party_caveat(f"expires<{expires_at_iso}")
    macaroon.add_first_party_caveat(f"max_depth<={max_depth}")

    return macaroon


def parse_identifier(macaroon: Macaroon) -> dict[str, Any]:
    """Parse and return the structured JSON identifier from a macaroon.

    Args:
        macaroon: Macaroon bearer token.

    Returns:
        dict[str, Any]: Parsed identifier dictionary containing human_subject_id,
            purpose, chain_id, and issued_at.

    Raises:
        json.JSONDecodeError: If identifier is not valid JSON.
    """
    raw_id = macaroon.identifier
    if isinstance(raw_id, bytes):
        raw_id = raw_id.decode("utf-8")
    return json.loads(raw_id)
