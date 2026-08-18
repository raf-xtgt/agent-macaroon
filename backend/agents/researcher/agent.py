"""Mid-chain agent responsible for gathering information and reading external content."""

import os
from typing import Any

from google.adk.agents import Agent

from agents.tool_caller.agent import tool_caller_agent

MODEL_NAME = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.5-flash")


def fetch_document(document_id: str) -> dict[str, Any]:
    """Mock fetch of an external/untrusted document — this is the injection surface.

    Real content screening (F5) attaches here in a later milestone via the Gateway
    Plugin, not inside this function.
    """
    return {
        "document_id": document_id,
        "text": "This is a mock document with no injected instructions.",
    }


researcher_agent = Agent(
    name="researcher_agent",
    model=MODEL_NAME,
    instruction="You gather information and external documents, delegating execution tasks to tool_caller_agent.",
    description="Gathers information and external documents, delegating execution tasks to tool_caller_agent.",
    tools=[fetch_document],
    sub_agents=[tool_caller_agent],
)
