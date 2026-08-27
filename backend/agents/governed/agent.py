"""Generic governed wrapper: secures any ADK fleet in target_fleet/ with agent-macaroon.

Auto-discovers the target fleet's root_agent, derives scope ceilings from its
agent tree, and wraps it in an App with GatewayPlugin attached. The target
fleet's code is never modified.

Usage:
    1. Drop (or symlink) your ADK agent package into backend/target_fleet/.
    2. Run: adk web ./agents/governed
    3. Optionally set TARGET_FLEET_PACKAGE to the Python package name
       (default: auto-detected from target_fleet/ contents).
    4. Optionally place a tool_map.py in agents/governed/ to override
       the default verb mapping (all tools -> "read").
"""

import importlib
import os
import sys
from pathlib import Path

from google.adk.apps import App

from gateway.adapters.adk_plugin import GatewayPlugin
from registry.agents_registry import AgentRegistry

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TARGET_FLEET_DIR = _BACKEND_DIR / "target_fleet"


def _discover_fleet_package() -> str:
    """Find the ADK agent package inside target_fleet/.

    Looks for directories containing an ``agent.py`` or ``__init__.py``.
    Returns the package name (directory name).
    """
    explicit = os.environ.get("TARGET_FLEET_PACKAGE")
    if explicit:
        return explicit

    if not _TARGET_FLEET_DIR.is_dir():
        raise RuntimeError(
            f"target_fleet/ directory not found at {_TARGET_FLEET_DIR}. "
            "Drop your ADK agent package there."
        )

    candidates = []
    for child in sorted(_TARGET_FLEET_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if (child / "agent.py").exists() or (child / "__init__.py").exists():
            candidates.append(child.name)

    if not candidates:
        raise RuntimeError(
            f"No ADK agent package found in {_TARGET_FLEET_DIR}/. "
            "The package must be a directory with agent.py or __init__.py."
        )
    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple agent packages found in target_fleet/: {candidates}. "
            "Set TARGET_FLEET_PACKAGE env var to pick one."
        )
    return candidates[0]


def _load_root_key() -> bytes:
    key = os.environ.get("AGENT_MACAROON_ROOT_KEY")
    if not key:
        raise RuntimeError(
            "AGENT_MACAROON_ROOT_KEY environment variable is not set or empty."
        )
    return key.encode("utf-8")


def _load_custom_tool_map() -> dict[str, str] | None:
    """Load a user-supplied tool map if it exists, else return None."""
    try:
        from .tool_map import TOOL_ACTION_MAP

        return TOOL_ACTION_MAP
    except (ImportError, AttributeError):
        return None


def _load_custom_initial_scope() -> set[str] | None:
    """Load a user-supplied initial scope if it exists, else return None."""
    try:
        from .tool_map import INITIAL_SCOPE

        return INITIAL_SCOPE
    except (ImportError, AttributeError):
        return None


# --- Discovery and import ---

_fleet_package = _discover_fleet_package()

_fleet_dir = str(_TARGET_FLEET_DIR)
if _fleet_dir not in sys.path:
    sys.path.insert(0, _fleet_dir)

# Some fleet packages (e.g., global_kyc_agent) call google.auth.default()
# on import — env vars must be set before this line.
_fleet_parent = str(_TARGET_FLEET_DIR.parent)
if _fleet_parent not in sys.path:
    sys.path.insert(0, _fleet_parent)

_fleet_module = importlib.import_module(f"{_fleet_package}.agent")
_fleet_root_agent = getattr(_fleet_module, "root_agent", None)
if _fleet_root_agent is None:
    raise RuntimeError(f"Package {_fleet_package}.agent does not export root_agent.")

# --- Configuration ---

_ROOT_KEY = _load_root_key()

_custom_tool_map = _load_custom_tool_map()
_custom_scope = _load_custom_initial_scope()

# If no custom tool map, auto-derive a default: all tools -> "read",
# delegation tools -> "delegate".
if _custom_tool_map is not None:
    _tool_map = _custom_tool_map
else:
    _tool_map = {}
    _derived_config = AgentRegistry.derive_from_agent_tree(_fleet_root_agent, {})

    # derive_from_agent_tree with empty map gives {} verbs for tools
    # but "delegate" for agents with sub_agents.
    # Build a default map: walk all tools and map them to "read".
    def _collect_tools(agent, result=None):
        if result is None:
            result = {}
        tools = getattr(agent, "tools", None) or []
        for tool in tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
            if name and name not in result:
                result[name] = "read"
        for sub in getattr(agent, "sub_agents", None) or []:
            _collect_tools(sub, result)
        return result

    _tool_map = _collect_tools(_fleet_root_agent)

if _custom_scope is not None:
    _initial_scope = _custom_scope
else:
    _initial_scope = set(_tool_map.values()) | {"delegate"}

# --- Registry ---

registry = AgentRegistry()
_derived = AgentRegistry.derive_from_agent_tree(_fleet_root_agent, _tool_map)
registry.register_bulk(_derived, owner="target-fleet")

# --- Plugin + App ---

_entry_agent_id = getattr(_fleet_root_agent, "name", "root_agent")

gateway_plugin = GatewayPlugin(
    root_key=_ROOT_KEY,
    registry=registry,
    initial_scope=_initial_scope,
    tool_action_map=_tool_map,
    entry_agent_id=_entry_agent_id,
    max_depth=8,
    enable_model_armor=True,
)

# Initialize Model Armor template (creates if not exists)
try:
    from armor.model_armor import ensure_template_exists

    ensure_template_exists()
except Exception:  # noqa: BLE001, S110
    pass  # Model Armor is optional; regex + gateway scope check are the primary defense

root_agent = _fleet_root_agent

app = App(
    name="agent_macaroon_governed",
    root_agent=root_agent,
    plugins=[gateway_plugin],
)
