"""ADK Plugin adapter enforcing fail-closed gateway policy across all lifecycle hooks."""

import hashlib
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

from armor.immunize import immunize_from_quarantine
from armor.model_armor import screen_with_model_armor
from armor.screen import screen_text
from audit.trace import emit_span
from gateway.policy import evaluate
from macaroon.attenuate import (
    DelegationDepthExceededError,
    attenuate,
    current_scope,
)
from macaroon.issue import issue_root_macaroon, parse_identifier
from macaroon.verify import verify_signature
from memory.behavior import recent_violation_count, record_denial
from registry.agents_registry import AgentRegistry

_DEFAULT_TOOL_ACTION_MAP: dict[str, str] = {
    "read_record": "read",
    "delete_record": "delete",
    "fetch_document": "fetch",
    "transfer_to_agent": "delegate",
}

MEMORY_VIOLATION_THRESHOLD: int = 3


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
        tool_action_map: dict[str, str] | None = None,
        entry_agent_id: str = "orchestrator_agent",
        max_depth: int = 5,
        enable_model_armor: bool = False,
    ) -> None:
        """Initialize the GatewayPlugin.

        Args:
            root_key: Secret root HMAC key for macaroon issuance and verification.
            registry: AgentRegistry instance for live scope ceiling lookups.
            initial_scope: Explicit set of action verbs granted to the root macaroon
                for every task (deliberate simplification: fixed grant per session
                without NLU task parsing).
            name: Unique name for this plugin instance.
            tool_action_map: Maps tool function names to abstract action verbs.
                Defaults to the built-in 3-agent demo map. Override when governing
                external fleets (e.g., global-kyc-agent).
            entry_agent_id: Name of the root/entry agent for the governed fleet.
            max_depth: Maximum delegation depth for minted macaroons.
            enable_model_armor: Whether to enable deep screening via Google Model Armor API.
        """
        super().__init__(name=name)
        self._root_key = root_key
        self._registry = registry
        self._initial_scope = initial_scope
        self._tool_action_map = tool_action_map or _DEFAULT_TOOL_ACTION_MAP
        self._entry_agent_id = entry_agent_id
        self._max_depth = max_depth
        self._enable_model_armor = enable_model_armor

    def _resolve_action(self, tool_name: str) -> str:
        """Map a tool name to an action verb via the configured map.

        ADK generates delegation tools named ``transfer_to_<agent_name>``; these
        are matched by prefix and mapped to ``"delegate"``.
        """
        action = self._tool_action_map.get(tool_name)
        if action is not None:
            return action
        if tool_name.startswith("transfer_to_"):
            return "delegate"
        return f"unknown_tool:{tool_name}"

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Mint the root macaroon for a task delegation chain on the first user message.

        Extracts human user identity and purpose text, attaches the plugin's initial scope,
        binds ADK's native invocation ID as the chain_id, emits the root audit span (F6),
        and stores the token and span pointer in session state.

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

            # F7: Check issuing agent's recent violation history to tighten initial scope if elevated
            violation_count = recent_violation_count(self._entry_agent_id)
            issuance_scope = self._initial_scope
            if (
                violation_count >= MEMORY_VIOLATION_THRESHOLD
                and "delete" in issuance_scope
            ):
                issuance_scope = issuance_scope - {"delete"}

            macaroon = issue_root_macaroon(
                human_subject_id=user_id,
                purpose=purpose,
                initial_scope=issuance_scope,
                root_key=self._root_key,
                chain_id=invocation_id,
                max_depth=self._max_depth,
            )

            raw_id = macaroon.identifier
            raw_id_bytes = raw_id.encode("utf-8") if isinstance(raw_id, str) else raw_id
            macaroon_hash = hashlib.sha256(raw_id_bytes).hexdigest()

            span_id = emit_span(
                chain_id=invocation_id,
                parent_span_id=None,
                agent_id=self._entry_agent_id,
                macaroon_identifier_hash=macaroon_hash,
                action_requested="issue_macaroon",
                decision="allow",
                reason="root macaroon issued",
                human_subject_id=user_id,
                purpose=purpose,
            )

            if hasattr(invocation_context, "session") and hasattr(
                invocation_context.session, "state"
            ):
                invocation_context.session.state["agent_macaroon"] = (
                    macaroon.serialize()
                )
                invocation_context.session.state["agent_macaroon_span"] = span_id
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
        registry ceiling, and writes the attenuated macaroon and updated span pointer back
        to session state. Emits audit spans for every allow and denial decision (F6).
        Fails closed on any missing token, invalid signature, or delegation depth exhaustion.

        Args:
            agent: The target agent about to execute.
            callback_context: Context for the agent execution.

        Returns:
            None if attenuation succeeds.
            types.Content containing denial text if delegation fails (short-circuiting the agent).
        """
        agent_name = getattr(agent, "name", "unknown_agent")

        parent_span_id: str | None = None
        raw_macaroon = None
        if hasattr(callback_context, "state") and callback_context.state is not None:
            parent_span_id = callback_context.state.get("agent_macaroon_span")
            raw_macaroon = callback_context.state.get("agent_macaroon")

        if not raw_macaroon or not isinstance(raw_macaroon, str):
            # Orphaned span: chain_id and identifier hash cannot be parsed because no token exists
            emit_span(
                chain_id=None,
                parent_span_id=parent_span_id,
                agent_id=agent_name,
                macaroon_identifier_hash=None,
                action_requested="transfer_to_agent",
                decision="deny",
                reason="No delegation macaroon found in session state.",
            )
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
            # Orphaned span: chain_id and identifier hash cannot be parsed due to deserialization failure
            emit_span(
                chain_id=None,
                parent_span_id=parent_span_id,
                agent_id=agent_name,
                macaroon_identifier_hash=None,
                action_requested="transfer_to_agent",
                decision="deny",
                reason="Failed to deserialize delegation macaroon.",
            )
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Denied: Failed to deserialize delegation macaroon."
                    )
                ],
            )

        # Extract identifier hash and chain_id from plaintext identifier
        macaroon_hash: str | None = None
        try:
            raw_id = macaroon.identifier
            raw_id_bytes = raw_id.encode("utf-8") if isinstance(raw_id, str) else raw_id
            macaroon_hash = hashlib.sha256(raw_id_bytes).hexdigest()
        except (AttributeError, UnicodeError, TypeError):
            macaroon_hash = None

        chain_id: str | None = None
        try:
            parsed_id = parse_identifier(macaroon)
            if isinstance(parsed_id, dict):
                chain_id = parsed_id.get("chain_id")
        except Exception:  # noqa: BLE001
            chain_id = None

        # Verify HMAC signature chain at delegation time
        if not verify_signature(macaroon, self._root_key):
            emit_span(
                chain_id=chain_id,
                parent_span_id=parent_span_id,
                agent_id=agent_name,
                macaroon_identifier_hash=macaroon_hash,
                action_requested="transfer_to_agent",
                decision="deny",
                reason="Invalid or tampered macaroon signature.",
            )
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Denied: Invalid or tampered macaroon signature."
                    )
                ],
            )

        curr_scope = current_scope(macaroon)

        try:
            attenuated = attenuate(
                macaroon=macaroon,
                to_agent_id=agent_name,
                task_required_scope=set(curr_scope),
                registry=self._registry,
            )
        except DelegationDepthExceededError as exc:
            emit_span(
                chain_id=chain_id,
                parent_span_id=parent_span_id,
                agent_id=agent_name,
                macaroon_identifier_hash=macaroon_hash,
                action_requested="transfer_to_agent",
                decision="deny",
                reason=f"Delegation depth exceeded: {exc}",
            )
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"Denied: Delegation depth exceeded: {exc}"
                    )
                ],
            )
        except Exception as exc:  # noqa: BLE001
            emit_span(
                chain_id=chain_id,
                parent_span_id=parent_span_id,
                agent_id=agent_name,
                macaroon_identifier_hash=macaroon_hash,
                action_requested="transfer_to_agent",
                decision="deny",
                reason=f"Macaroon attenuation failed: {exc}",
            )
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=f"Denied: Macaroon attenuation failed: {exc}"
                    )
                ],
            )

        attenuated_raw_id = attenuated.identifier
        attenuated_raw_bytes = (
            attenuated_raw_id.encode("utf-8")
            if isinstance(attenuated_raw_id, str)
            else attenuated_raw_id
        )
        attenuated_hash = hashlib.sha256(attenuated_raw_bytes).hexdigest()

        span_id = emit_span(
            chain_id=chain_id,
            parent_span_id=parent_span_id,
            agent_id=agent_name,
            macaroon_identifier_hash=attenuated_hash,
            action_requested="transfer_to_agent",
            decision="allow",
            reason="attenuated",
        )

        callback_context.state["agent_macaroon"] = attenuated.serialize()
        callback_context.state["agent_macaroon_span"] = span_id
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
        ADK's context, evaluates the gateway policy, and emits an audit span (F6).

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
        requested_action = self._resolve_action(tool_name)
        presenting_agent_id = getattr(tool_context, "agent_name", "unknown")

        decision = evaluate(
            macaroon=macaroon,
            requested_action=requested_action,
            presenting_agent_id=presenting_agent_id,
            root_key=self._root_key,
            registry=self._registry,
        )

        # F7: Read recent violation count before recording this invocation's outcome
        violation_count = recent_violation_count(decision.presenting_agent_id)
        if not decision.allowed:
            record_denial(
                agent_id=decision.presenting_agent_id,
                chain_id=decision.chain_id,
                reason=decision.reason,
                timestamp=decision.timestamp,
            )

        span_reason = decision.reason
        if violation_count >= MEMORY_VIOLATION_THRESHOLD:
            span_reason = (
                f"{decision.reason} [Memory Bank flag: {violation_count} "
                f"recent denials for {decision.presenting_agent_id}]"
            )

        parent_span_id: str | None = None
        state = getattr(tool_context, "state", None)
        if state is not None:
            parent_span_id = state.get("agent_macaroon_span")

        emit_span(
            chain_id=decision.chain_id,
            parent_span_id=parent_span_id,
            agent_id=decision.presenting_agent_id,
            macaroon_identifier_hash=decision.macaroon_identifier_hash,
            action_requested=decision.requested_action,
            decision="allow" if decision.allowed else "deny",
            reason=span_reason,
            timestamp=decision.timestamp,
        )

        if decision.allowed:
            return None

        return {
            "error": "denied_by_gateway",
            "reason": decision.reason,
        }

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Screen tool output for prompt injection and quarantine flagged content.

        Evaluates every string value in the tool result dictionary against Model Armor
        injection detection patterns. If any field matches an injection signature,
        replaces the value with a quarantine notice while preserving non-flagged and
        non-string fields. Emits a content screening audit span (F6).

        Args:
            tool: The tool instance that was executed.
            tool_args: The arguments passed to the tool.
            tool_context: The ADK execution context.
            result: The dictionary returned by the tool execution.

        Returns:
            dict[str, Any] | None: Modified dictionary if flagged, or None if clean.
        """
        if not isinstance(result, dict):
            return None

        quarantined: dict[str, Any] = {}
        has_quarantine = False
        ma_confidences: list[str] = []

        for key, value in result.items():
            if isinstance(value, str):
                screen_res = screen_text(value)
                if screen_res.flagged:
                    patterns_str = ", ".join(screen_res.matched_patterns)
                    quarantined[key] = (
                        f"[CONTENT QUARANTINED BY MODEL ARMOR: "
                        f"potential prompt injection detected — pattern: {patterns_str}]"
                    )
                    has_quarantine = True

                    # Also call Model Armor for confidence data if enabled
                    if self._enable_model_armor:
                        try:
                            ma_result = screen_with_model_armor(value)
                            if ma_result.flagged:
                                quarantined[key] += (
                                    f" [Model Armor: PI/jailbreak={ma_result.pi_and_jailbreak_detected}, "
                                    f"confidence={ma_result.confidence_level}]"
                                )
                                if ma_result.confidence_level:
                                    ma_confidences.append(
                                        f"confidence={ma_result.confidence_level}"
                                    )
                        except Exception:  # noqa: BLE001, S110
                            pass

                    # Immunize: register a runtime pattern to catch similar payloads earlier
                    try:
                        immunize_from_quarantine(
                            quarantined_text=value,
                            agent_id=getattr(tool_context, "agent_name", "unknown"),
                            registry=self._registry,
                            tighten_verbs=None,
                        )
                    except Exception:  # noqa: BLE001, S110
                        pass
                else:
                    quarantined[key] = value

                    # Model Armor deep screen on content that passed regex
                    if self._enable_model_armor:
                        try:
                            ma_result = screen_with_model_armor(value)
                            if ma_result.flagged:
                                quarantined[key] = (
                                    f"[CONTENT QUARANTINED BY MODEL ARMOR (ML): "
                                    f"PI/jailbreak detected — confidence: {ma_result.confidence_level}]"
                                )
                                has_quarantine = True
                                if ma_result.confidence_level:
                                    ma_confidences.append(
                                        f"confidence={ma_result.confidence_level}"
                                    )

                                # Immunize from the ML-detected content too
                                try:
                                    immunize_from_quarantine(
                                        quarantined_text=value,
                                        agent_id=getattr(
                                            tool_context, "agent_name", "unknown"
                                        ),
                                        registry=self._registry,
                                        tighten_verbs=None,
                                    )
                                except Exception:  # noqa: BLE001, S110
                                    pass
                        except Exception:  # noqa: BLE001, S110
                            pass
            else:
                quarantined[key] = value

        parent_span_id: str | None = None
        raw_macaroon = None
        state = getattr(tool_context, "state", None)
        if state is not None:
            parent_span_id = state.get("agent_macaroon_span")
            raw_macaroon = state.get("agent_macaroon")

        macaroon: Macaroon | None = None
        if isinstance(raw_macaroon, str) and raw_macaroon:
            try:
                macaroon = Macaroon.deserialize(raw_macaroon)
            except (
                MacaroonException,
                ValueError,
                TypeError,
                AttributeError,
                UnicodeError,
            ):
                macaroon = None

        macaroon_hash: str | None = None
        chain_id: str | None = None
        if macaroon is not None:
            try:
                raw_id = macaroon.identifier
                raw_id_bytes = (
                    raw_id.encode("utf-8") if isinstance(raw_id, str) else raw_id
                )
                macaroon_hash = hashlib.sha256(raw_id_bytes).hexdigest()
            except (AttributeError, UnicodeError, TypeError):
                macaroon_hash = None

            try:
                parsed_id = parse_identifier(macaroon)
                if isinstance(parsed_id, dict):
                    chain_id = parsed_id.get("chain_id")
            except Exception:  # noqa: BLE001
                chain_id = None

        tool_name = getattr(tool, "name", "")
        agent_id = getattr(tool_context, "agent_name", "unknown")

        if has_quarantine:
            quarantined_keys = sorted(quarantined.keys())
            span_reason = f"quarantined fields: {quarantined_keys}"
            if ma_confidences:
                span_reason += f" [Model Armor: {', '.join(ma_confidences)}]"
            emit_span(
                chain_id=chain_id,
                parent_span_id=parent_span_id,
                agent_id=agent_id,
                macaroon_identifier_hash=macaroon_hash,
                action_requested=f"screen:{tool_name}",
                decision="deny",
                reason=span_reason,
            )
            return quarantined

        emit_span(
            chain_id=chain_id,
            parent_span_id=parent_span_id,
            agent_id=agent_id,
            macaroon_identifier_hash=macaroon_hash,
            action_requested=f"screen:{tool_name}",
            decision="allow",
            reason="clean",
        )
        return None
