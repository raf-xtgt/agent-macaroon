"""Leaf agent responsible for executing side-effecting actions via tools."""

import os
from typing import Any

from google.adk.agents import Agent

MODEL_NAME = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.5-flash")


def read_record(record_id: str) -> dict[str, Any]:
    """Mock read of a record by ID. Placeholder tool for the pre-Gateway skeleton."""
    return {"record_id": record_id, "content": "mock record content", "action": "read"}


def delete_record(record_id: str) -> dict[str, Any]:
    """Mock delete of a record by ID. Placeholder tool for the pre-Gateway skeleton."""
    return {"record_id": record_id, "status": "deleted", "action": "delete"}


tool_caller_agent = Agent(
    name="tool_caller_agent",
    model=MODEL_NAME,
    instruction="You execute side-effecting actions and data operations via available tools.",
    description="Executes side-effecting actions and data operations via tools.",
    tools=[read_record, delete_record],
)
