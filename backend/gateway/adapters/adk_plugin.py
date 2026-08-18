"""ADK Plugin adapter enforcing fail-closed gateway policy across all lifecycle hooks."""

import uuid
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pymacaroons import Macaroon
from pymacaroons.exceptions import MacaroonException

from gateway.policy import evaluate
from macaroon.attenuate import (
    DelegationDepthExceededError,
    attenuate,
    current_scope,
)
from macaroon.issue import issue_root_macaroon
from macaroon.verify import verify_signature
from registry.agents_registry import AgentRegistry

TOOL_ACTION_MAP: dict[str, str] = {
    "read_record": "read",
    "delete_record": "delete",
    "fetch_document": "fetch",
}


class GatewayPlugin(BasePlugin):
    """ADK BasePlugin adapter for capability-based gateway enforcement.

    Attaches at the App/Runner level to govern task delegation, intercepting user
    messages to mint root macaroons (F1), attenuating scope across agent handoffs (F2),
    and verifying macaroons before tool calls against live registry ceilings (F4).
    """

    def __init__(
        self,
        root_key: bytes,
        registry: AgentRegistry,
        initial_scope: set[str],
        name: str = "gateway_plugin",
    ) -> None:
        """Initialize the GatewayPlugin.

        Args:
            root_key: Secret root HMAC key for macaroon issuance and verification.
            registry: AgentRegistry instance for live scope ceiling lookups.
            initial_scope: Explicit set of action verbs granted to the root macaroon
                for every task (deliberate simplification: fixed grant per session
                without NLU task parsing).
            name: Unique name for this plugin instance.
        """
        super().__init__(name=name)
        self._root_key = root_key
        self._registry = registry
        self._initial_scope = initial_scope

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Mint the root macaroon for a task delegation chain on the first user message.

        Extracts human user identity and purpose text, attaches the plugin's initial scope,
        and binds ADK's native invocation ID as the chain_id in session state.

        Args:
            invocation_context: Context for the overall invocation, holding session state.
            user_message: Incoming user message content.

        Returns:
            None: Never interrupts session execution.
        """
        try:
            user_id = getattr(invocation_context, "user_id", "anonymous_user")
            invocation_id = getattr(
                invocation_context, "invocation_id", str(uuid.uuid4())
            )

            purpose_parts: list[str] = []
            if hasattr(user_message, "parts") and user_message.parts:
                for part in user_message.parts:
                    if hasattr(part, "text") and part.text:
                        purpose_parts.append(part.text.strip())

            purpose = (
                " ".join(purpose_parts).strip()
                if purpose_parts
                else "(no text content)"
            )

            macaroon = issue_root_macaroon(
                human_subject_id=user_id,
                purpose=purpose,
                initial_scope=self._initial_scope,
                root_key=self._root_key,
                chain_id=invocation_id,
            )

            if hasattr(invocation_context, "session") and hasattr(
                invocation_context.session, "state"
            ):
                invocation_context.session.state["agent_macaroon"] = (
                    macaroon.serialize()
                )
        except Exception:  # noqa: BLE001, S110
            # F1 must never crash an entire session on token minting failure
            pass

        return None

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        """Attenuate the macaroon before an agent executes.

        Fires uniformly across all agent handoffs (including entry agent). Verifies the
        macaroon HMAC signature, computes scope intersection with the target agent's
        registry ceiling, and writes the attenuated macaroon back to session state.
        Fails closed on any missing token, invalid signature, or delegation depth exhaustion.

        Args:
            agent: The target agent about to execute.
            callback_context: Context for the agent execution.

        Returns:
            None if attenuation succeeds.
            types.Content containing denial text if delegation fails (short-circuiting the agent).
        """
        raw_macaroon = None
        if hasattr(callback_context, "state") and callback_context.state is not None:
            raw_macaroon = callback_context.state.get("agent_macaroon")

        if not raw_macaroon or not isinstance(raw_macaroon, str):
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Denied: No delegation macaroon found in session state."
                    )
                ],
            )

        try:
            macaroon = Macaroon.deserialize(raw_macaroon)
        except (
            MacaroonException,
            ValueError,
            TypeError,
            AttributeError,
            UnicodeError,
        ):
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Denied: Failed to deserialize delegation macaroon."
                    )
                ],
            )

        # Verify HMAC signature chain at delegation time
        if not verify_signature(macaroon, self._root_key):
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Denied: Invalid or tampered macaroon signature."
                    )
                ],
            )

        agent_name = getattr(agent, "name", "unknown_agent")
        curr_scope = current_scope(macaroon)

        try:
            attenuated = attenuate(
                macaroon=macaroon,
                to_agent_id=agent_name,
                task_required_scope=set(curr_scope),
                registry=self._registry,
            )
        except DelegationDepthExceededError as exc:
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"Denied: Delegation depth exceeded: {exc}"
                    )
                ],
            )
        except Exception as exc:  # noqa: BLE001
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"Denied: Macaroon attenuation failed: {exc}"
                    )
                ],
            )

        callback_context.state["agent_macaroon"] = attenuated.serialize()
        return None

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
