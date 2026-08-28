"""FastAPI application entrypoint merging ADK agent serving and audit API into a single deployable."""

import sys
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from google.adk.cli.fast_api import get_fast_api_app

from armor.api import router as armor_router
from audit.api import router as audit_router
from red_team.api import router as red_team_router

# Alias pre-imported agents.* packages so ADK's AgentLoader reuses module instances.
for agent_pkg in ("orchestrator", "researcher", "tool_caller", "governed"):
    if f"agents.{agent_pkg}" in sys.modules and agent_pkg not in sys.modules:
        sys.modules[agent_pkg] = sys.modules[f"agents.{agent_pkg}"]
    if (
        f"agents.{agent_pkg}.agent" in sys.modules
        and f"{agent_pkg}.agent" not in sys.modules
    ):
        sys.modules[f"{agent_pkg}.agent"] = sys.modules[f"agents.{agent_pkg}.agent"]

_AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")

_ALLOWED_ORIGINS = ["http://localhost:3000", "https://localhost:3000"]

app = get_fast_api_app(
    agents_dir=_AGENTS_DIR,
    web=False,
    allow_origins=_ALLOWED_ORIGINS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(audit_router)
app.include_router(red_team_router)
app.include_router(armor_router)
