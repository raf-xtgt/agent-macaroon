"""First-party caveat addition and cryptographic scope attenuation."""

from pymacaroons import Macaroon

from registry.agents_registry import AgentRegistry


class DelegationDepthExceededError(Exception):
    """Raised when delegation depth reaches 0 and further attenuation is attempted."""


def _extract_current_scope(macaroon: Macaroon) -> set[str]:
    """Extract the effective scope from the last 'scope=' caveat in the macaroon."""
    scopes: list[set[str]] = []
    for caveat in macaroon.first_party_caveats():
        cid = (
            caveat.caveat_id
            if isinstance(caveat.caveat_id, str)
            else caveat.caveat_id.decode("utf-8")
        )
        if cid.startswith("scope="):
            raw = cid.removeprefix("scope=").strip()
            if not raw:
                scopes.append(set())
            else:
                scopes.append({a.strip() for a in raw.split(",") if a.strip()})

    if not scopes:
        return set()
    return scopes[-1]


def _extract_remaining_depth(macaroon: Macaroon, default_depth: int = 5) -> int:
    """Extract the remaining delegation depth from the last 'max_depth<=' caveat."""
    depths: list[int] = []
    for caveat in macaroon.first_party_caveats():
        cid = (
            caveat.caveat_id
            if isinstance(caveat.caveat_id, str)
            else caveat.caveat_id.decode("utf-8")
        )
        if cid.startswith("max_depth<="):
            try:
                depths.append(int(cid.removeprefix("max_depth<=").strip()))
            except (ValueError, TypeError):
                continue

    if not depths:
        return default_depth
    return depths[-1]


def attenuate(
    macaroon: Macaroon,
    to_agent_id: str,
    task_required_scope: set[str],
    registry: AgentRegistry,
) -> Macaroon:
    """Attenuate a macaroon for delegation to a downstream agent.

    Computes effective authority via scope intersection:
        new_scope = current_scope ∩ task_required_scope ∩ registry.ceiling(to_agent_id)

    Appends chained first-party caveats in order:
        1. scope=<new_scope>
        2. agent=<to_agent_id>
        3. max_depth<=<remaining_depth - 1>

    Fails closed: if remaining delegation depth is <= 0, raises DelegationDepthExceededError.
    If new_scope is empty, returns a valid macaroon with empty scope caveat (authorizes nothing).

    Args:
        macaroon: Current macaroon bearer token.
        to_agent_id: Identifier of the target agent receiving delegation.
        task_required_scope: Set of action verbs requested for this specific task hop.
        registry: AgentRegistry instance for looking up scope ceilings.

    Returns:
        Macaroon: Attenuated macaroon with new caveats appended.

    Raises:
        DelegationDepthExceededError: If remaining delegation depth is <= 0.
    """
    remaining_depth = _extract_remaining_depth(macaroon)
    if remaining_depth <= 0:
        raise DelegationDepthExceededError(
            f"Cannot attenuate macaroon: remaining delegation depth is {remaining_depth}"
        )

    current_scope = _extract_current_scope(macaroon)
    agent_ceiling = set(registry.ceiling(to_agent_id))

    new_scope = current_scope & task_required_scope & agent_ceiling

    attenuated = macaroon.copy()
    scope_str = ",".join(sorted(new_scope))
    attenuated.add_first_party_caveat(f"scope={scope_str}")
    attenuated.add_first_party_caveat(f"agent={to_agent_id}")
    attenuated.add_first_party_caveat(f"max_depth<={remaining_depth - 1}")

    return attenuated
