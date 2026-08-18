"""Root orchestrator agent receiving human task requests and delegating to specialist agents."""

import os

from google.adk.agents import Agent
from google.adk.apps import App

from agents.researcher.agent import researcher_agent
from gateway.adapters.adk_plugin import GatewayPlugin
from registry.agents_registry import AgentRegistry


def _load_root_key() -> bytes:
    """Load the HMAC root key from the AGENT_MACAROON_ROOT_KEY environment variable.

    Returns:
        bytes: UTF-8 encoded secret root key.

    Raises:
        RuntimeError: If AGENT_MACAROON_ROOT_KEY is unset or empty.
    """
    key = os.environ.get("AGENT_MACAROON_ROOT_KEY")
    if not key:
        raise RuntimeError(
            "AGENT_MACAROON_ROOT_KEY environment variable is not set or empty. "
            "Set it to a secure secret string for macaroon HMAC operations."
        )
    return key.encode("utf-8")


MODEL_NAME = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.5-flash")

orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=MODEL_NAME,
    instruction="You receive human task requests and coordinate workflow execution by delegating to researcher_agent.",
    description="Receives human tasks and coordinates workflow execution by delegating to researcher_agent.",
    sub_agents=[researcher_agent],
)

root_agent = orchestrator_agent

# Initialize the Agent Registry with scope ceilings for all 3 agents
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

# Instantiate the GatewayPlugin with the root key, shared registry, and initial scope
gateway_plugin = GatewayPlugin(
    root_key=_load_root_key(),
    registry=registry,
    initial_scope={"read", "fetch", "delete"},
)

# Construct the governed App wrapping the agent chain
app = App(
    name="agent_macaroon_governed_chain",
    root_agent=orchestrator_agent,
    plugins=[gateway_plugin],
)
