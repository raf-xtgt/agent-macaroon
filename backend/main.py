"""FastAPI application entrypoint merging ADK agent serving and audit API into a single deployable."""

import sys
from pathlib import Path

from google.adk.cli.fast_api import get_fast_api_app

from audit.api import router as audit_router

# Alias any pre-imported agents.* packages so ADK's AgentLoader reuses the same module instances
for agent_pkg in ("orchestrator", "researcher", "tool_caller"):
    if f"agents.{agent_pkg}" in sys.modules and agent_pkg not in sys.modules:
        sys.modules[agent_pkg] = sys.modules[f"agents.{agent_pkg}"]
    if (
        f"agents.{agent_pkg}.agent" in sys.modules
        and f"{agent_pkg}.agent" not in sys.modules
    ):
        sys.modules[f"{agent_pkg}.agent"] = sys.modules[f"agents.{agent_pkg}.agent"]

_AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")

app = get_fast_api_app(agents_dir=_AGENTS_DIR, web=False)
app.include_router(audit_router)
