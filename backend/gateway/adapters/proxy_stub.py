"""Stub adapter: generic HTTP endpoint for non-ADK frameworks (LangChain, AWS Strands, etc.).

Proves the enforcement core is framework-agnostic; selected via GATEWAY_MODE=proxy,
never exercised in the demo. See agent-specification.md §13.
"""

import os
import sys
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from pymacaroons import Macaroon
from pymacaroons.exceptions import MacaroonException

from gateway.policy import evaluate
from registry.agents_registry import AgentRegistry


class EvaluateRequest(BaseModel):
    """Request payload for the proxy-stub /evaluate endpoint."""

    macaroon: str | None = None
    requested_action: str
    presenting_agent_id: str


def create_proxy_app(root_key: bytes, registry: AgentRegistry) -> FastAPI:
    """Build the non-ADK proxy-stub gateway: one POST /evaluate endpoint wrapping
    gateway.policy.evaluate(). See agent-specification.md §13 — a stub proving the
    enforcement core is framework-agnostic, not a production non-ADK integration.
    """
    app = FastAPI(
        title="Agent Macaroon Proxy Stub Gateway",
        description="Non-ADK proxy stub adapter proving framework-agnostic capability enforcement.",
        version="0.1.0",
    )

    @app.post("/evaluate")
    def evaluate_endpoint(request: EvaluateRequest) -> dict[str, Any]:
        """Evaluate capability token and return fail-closed gateway decision as JSON."""
        macaroon: Macaroon | None = None
        if request.macaroon is not None:
            try:
                macaroon = Macaroon.deserialize(request.macaroon)
            except (
                MacaroonException,
                ValueError,
                TypeError,
                AttributeError,
                UnicodeError,
            ):
                macaroon = None

        decision = evaluate(
            macaroon=macaroon,
            requested_action=request.requested_action,
            presenting_agent_id=request.presenting_agent_id,
            root_key=root_key,
            registry=registry,
        )

        return {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "requested_action": decision.requested_action,
            "presenting_agent_id": decision.presenting_agent_id,
            "macaroon_identifier_hash": decision.macaroon_identifier_hash,
            "chain_id": decision.chain_id,
            "timestamp": decision.timestamp.isoformat(),
        }

    return app


def _build_default_registry() -> AgentRegistry:
    """Same three agents/ceilings as agents/orchestrator/agent.py, duplicated here on purpose —
    this is a stub never exercised in the demo, not worth coupling to the real chain's module.
    """
    registry = AgentRegistry()
    registry.register(
        agent_id="orchestrator_agent",
        display_name="Orchestrator",
        max_scope={"read", "fetch", "delete"},
        owner="platform-team",
    )
    registry.register(
        agent_id="researcher_agent",
        display_name="Researcher",
        max_scope={"read", "fetch"},
        owner="research-team",
    )
    registry.register(
        agent_id="tool_caller_agent",
        display_name="Tool Caller",
        max_scope={"read", "delete"},
        owner="execution-team",
    )
    return registry


if __name__ == "__main__":
    mode = os.environ.get("GATEWAY_MODE", "adk")
    if mode != "proxy":
        print(
            f"Refusing to start proxy stub: GATEWAY_MODE is '{mode}', expected 'proxy'. "
            "Set GATEWAY_MODE=proxy to run this adapter.",
            file=sys.stderr,
        )
        sys.exit(1)

    key = os.environ.get("AGENT_MACAROON_ROOT_KEY")
    if not key:
        raise RuntimeError(
            "AGENT_MACAROON_ROOT_KEY environment variable is not set or empty. "
            "Set it to a secure secret string for macaroon HMAC operations."
        )
    root_key = key.encode("utf-8")
    app = create_proxy_app(root_key=root_key, registry=_build_default_registry())
    uvicorn.run(app, host="0.0.0.0", port=8001)
