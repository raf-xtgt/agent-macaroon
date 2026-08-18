"""Macaroon token issuance, attenuation, and verification package."""

from macaroon.attenuate import DelegationDepthExceededError, attenuate
from macaroon.issue import issue_root_macaroon, parse_identifier
from macaroon.verify import (
    CaveatCheckResult,
    VerificationContext,
    verify_caveats,
    verify_macaroon,
    verify_signature,
)

__all__ = [
    "CaveatCheckResult",
    "DelegationDepthExceededError",
    "VerificationContext",
    "attenuate",
    "issue_root_macaroon",
    "parse_identifier",
    "verify_caveats",
    "verify_macaroon",
    "verify_signature",
]
