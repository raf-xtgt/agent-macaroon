"""Root orchestrator agent receiving human task requests and delegating to specialist agents."""

import os

from google.adk.agents import Agent

from agents.researcher.agent import researcher_agent

MODEL_NAME = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.5-flash")

orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=MODEL_NAME,
    instruction="You receive human task requests and coordinate workflow execution by delegating to researcher_agent.",
    description="Receives human tasks and coordinates workflow execution by delegating to researcher_agent.",
    sub_agents=[researcher_agent],
)

root_agent = orchestrator_agent
