"""ADK Plugin adapter enforcing fail-closed gateway policy on all tool invocations."""

from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from pymacaroons import Macaroon
from pymacaroons.exceptions import MacaroonException

from gateway.policy import evaluate
from registry.agents_registry import AgentRegistry

TOOL_ACTION_MAP: dict[str, str] = {
    "read_record": "read",
    "delete_record": "delete",
    "fetch_document": "fetch",
}


class GatewayPlugin(BasePlugin):
    """ADK BasePlugin adapter for capability-based gateway enforcement.

    Attaches at the App/Runner level to intercept all tool executions, verifying
    bearer macaroons against cryptographic caveats and live Agent Registry ceilings.
    """

    def __init__(
        self,
        root_key: bytes,
        registry: AgentRegistry,
        name: str = "gateway_plugin",
    ) -> None:
        """Initialize the GatewayPlugin.

        Args:
            root_key: Secret root HMAC key for macaroon verification.
            registry: AgentRegistry instance for live scope ceiling lookups.
            name: Unique name for this plugin instance.
        """
        super().__init__(name=name)
        self._root_key = root_key
        self._registry = registry

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Intercept a tool execution before invocation and enforce gateway policy.

        Reads the serialized macaroon from session state ('agent_macaroon'), maps
        the tool name to an action verb, resolves the executing agent identity from
        ADK's context, and evaluates the gateway policy.

        Args:
            tool: The tool instance being called.
            tool_args: The arguments passed to the tool.
            tool_context: The ADK execution context containing state and agent identity.

        Returns:
            None if the action is authorized (allowing tool execution).
            dict[str, Any] containing error and reason if denied (halting tool execution).
        """
        macaroon: Macaroon | None = None
        try:
            state = getattr(tool_context, "state", None)
            if state is not None:
                raw_macaroon = state.get("agent_macaroon")
                if isinstance(raw_macaroon, str) and raw_macaroon:
                    macaroon = Macaroon.deserialize(raw_macaroon)
        except (
            MacaroonException,
            ValueError,
            TypeError,
            AttributeError,
            UnicodeError,
        ):
            macaroon = None

        tool_name = getattr(tool, "name", "")
        requested_action = TOOL_ACTION_MAP.get(tool_name, f"unknown_tool:{tool_name}")
        presenting_agent_id = getattr(tool_context, "agent_name", "unknown")

        decision = evaluate(
            macaroon=macaroon,
            requested_action=requested_action,
            presenting_agent_id=presenting_agent_id,
            root_key=self._root_key,
            registry=self._registry,
        )

        if decision.allowed:
            return None

        return {
            "error": "denied_by_gateway",
            "reason": decision.reason,
        }
