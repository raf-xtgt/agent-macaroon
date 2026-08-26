"""Framework-agnostic content-based injection screening layer (F5).

Screens untrusted content (tool outputs, documents, external text) for known
prompt injection patterns seeded from AgentDojo and InjecAgent attack corpora.
"""

import re
from dataclasses import dataclass

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "agentdojo_ignore_previous": re.compile(
        r"ignore\s+(your\s+)?previous\s+i?u?nstructions", re.IGNORECASE
    ),
    "agentdojo_system_message_delimiter": re.compile(
        r"#{2,}\s*\(?\s*system[\s_-]*message\s*\)?", re.IGNORECASE
    ),
    "agentdojo_injecagent_important_override": re.compile(
        r"important!{2,}.{0,80}ignore\s+all\s+previous\s+instructions",
        re.IGNORECASE | re.DOTALL,
    ),
    # --- KYC/compliance-specific patterns ---
    # Role hijacking: attacker tries to reassign the agent's identity
    "role_hijack": re.compile(
        r"(?:you\s+are\s+now|from\s+now\s+on\s+(?:you\s+are|respond\s+as|act\s+as)|your\s+new\s+role\s+is)",
        re.IGNORECASE,
    ),
    # Output manipulation: attacker tries to dictate report conclusions
    # Requires imperative framing ("you must", "you should", "you need to") to avoid
    # flagging legitimate instructions like "in your report, state that the company was incorporated in 2005"
    "output_manipulation": re.compile(
        r"(?:(?:you\s+(?:must|should|need\s+to|have\s+to)\s+)?in\s+your\s+(?:report|response|output|summary),?\s*(?:state|conclude|write|say|indicate|mark)\s+that\s+(?:this|the|there\s+are\s+no|everything\s+is)\s+(?:company\s+(?:is|has)\s+(?:no|compliant|clean)|compliant|clean|approved))",
        re.IGNORECASE,
    ),
    # Data exfiltration: attacker tries to expand scope to additional entities
    # Requires a second-person directive ("you must also", "you should also") or
    # imperative framing to avoid flagging normal phrases like "also look up the filing history"
    "scope_expansion": re.compile(
        r"(?:you\s+(?:must|should|need\s+to)\s+also\s+(?:look\s+up|retrieve|search\s+for|fetch|get|find|query)|"
        r"additionally\s+(?:retrieve|search|fetch|get|query)\s+(?:data|information|records|details)\s+(?:for|about|on)\s|"
        r"while\s+you(?:'re|\s+are)\s+at\s+it,?\s*(?:also|get|fetch|retrieve))",
        re.IGNORECASE,
    ),
    # Context manipulation: attacker tries to redefine the conversation context
    "context_override": re.compile(
        r"(?:disregard\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:context|instructions|rules|guidelines)|"
        r"new\s+context:\s|override\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|context|rules))",
        re.IGNORECASE,
    ),
    # Fake authority: attacker impersonates a system or admin
    "fake_authority": re.compile(
        r"(?:\[(?:system|admin|root|supervisor)\]|"
        r"(?:as\s+(?:the\s+)?(?:system|admin|administrator|supervisor),?\s+I\s+(?:instruct|order|direct|command))|"
        r"by\s+(?:order|authority|directive)\s+of\s+(?:the\s+)?(?:system|admin|administrator|compliance\s+officer))",
        re.IGNORECASE,
    ),
    # Encoding/obfuscation: base64-encoded instruction blocks
    "encoded_instruction": re.compile(
        r"(?:decode\s+(?:and\s+)?(?:execute|follow|run)|"
        r"base64[\s:]+[A-Za-z0-9+/=]{20,}|"
        r"the\s+following\s+(?:encoded|base64|hex)\s+(?:instruction|message|command))",
        re.IGNORECASE,
    ),
    # Urgency/override: attacker creates false urgency to bypass reasoning
    "urgency_override": re.compile(
        r"(?:critical\s*(?:!+|:)\s*(?:you\s+must|immediately|override|bypass)|"
        r"emergency\s*(?:!+|:)\s*(?:override|bypass|skip|ignore)\s+(?:all\s+)?(?:checks|rules|restrictions|protocols)|"
        r"urgent\s*(?:!+|:)\s*(?:skip|bypass|ignore)\s+(?:all\s+)?(?:verification|checks|protocols))",
        re.IGNORECASE,
    ),
    # Tool instruction injection: attacker directly instructs tool usage
    # Requires imperative framing ("you must", "now") to avoid "call the tool support vendor"
    "tool_instruction": re.compile(
        r"(?:(?:you\s+must|you\s+need\s+to|now)\s+call\s+(?:the\s+)?(?:function|tool|api)\s|"
        r"execute\s+(?:the\s+)?(?:following\s+)?(?:function|tool|command|api)\s|"
        r"invoke\s+(?:the\s+)?(?:function|tool)\s+\w+\s*\()",
        re.IGNORECASE,
    ),
    # Compliance report falsification: specific to KYC domain
    # The second alternative requires imperative framing to avoid flagging legitimate clean results
    "compliance_falsification": re.compile(
        r"(?:mark\s+(?:this|the)\s+(?:company|entity|person|officer)\s+as\s+(?:compliant|clean|approved|cleared|low[\s-]?risk)|"
        r"(?:you\s+(?:must|should|need\s+to)\s+)?(?:report|state|indicate|write|conclude)\s+(?:that\s+)?(?:no|zero|clean)\s+(?:compliance|regulatory|legal)\s+(?:issues?|violations?|concerns?|flags?)|"
        r"override\s+(?:the\s+)?(?:compliance|risk|regulatory)\s+(?:score|rating|assessment|flag))",
        re.IGNORECASE,
    ),
}

# Runtime patterns added by the immunization system after blocked attacks.
# These are in addition to the static INJECTION_PATTERNS above.
_runtime_patterns: dict[str, re.Pattern[str]] = {}


def add_runtime_pattern(name: str, pattern: str) -> None:
    """Add a new injection pattern at runtime (immunization).

    Called by the immunization module after a blocked attack. The pattern
    is compiled and added to the runtime set. It will be checked by
    screen_text() alongside the static patterns.

    Args:
        name: Unique name for the pattern (prefixed with "immunized_" by convention).
        pattern: Raw regex string to compile.
    """
    _runtime_patterns[name] = re.compile(pattern, re.IGNORECASE | re.DOTALL)


def get_active_pattern_count() -> int:
    """Return the total number of active patterns (static + runtime)."""
    return len(INJECTION_PATTERNS) + len(_runtime_patterns)


def list_runtime_patterns() -> list[str]:
    """Return the names of all runtime-added patterns."""
    return list(_runtime_patterns.keys())


@dataclass(frozen=True)
class ScreenResult:
    """Result of content-based prompt injection screening.

    Attributes:
        flagged: True if one or more injection patterns matched.
        matched_patterns: Names of every pattern that matched (empty tuple if clean).
        reason: Descriptive explanation of detected injection signatures, or None if clean.
    """

    flagged: bool
    matched_patterns: tuple[str, ...]
    reason: str | None


def screen_text(text: str) -> ScreenResult:
    """Screen plain text for prompt injection patterns.

    Framework-agnostic content screen with no ADK dependencies. Plain string in,
    ScreenResult out, matching the core/adapter split established for gateway/policy.py.

    Args:
        text: Plain text content to screen for prompt injection signatures.

    Returns:
        ScreenResult: Result indicating whether any pattern was matched, the tuple of
            matched pattern names, and a formatted reason string.
    """
    matched: list[str] = []
    for pattern_name, regex in INJECTION_PATTERNS.items():
        if regex.search(text):
            matched.append(pattern_name)
    for pattern_name, regex in _runtime_patterns.items():
        if regex.search(text):
            matched.append(pattern_name)

    if matched:
        matched_tuple = tuple(matched)
        return ScreenResult(
            flagged=True,
            matched_patterns=matched_tuple,
            reason=f"potential prompt injection detected: {', '.join(matched_tuple)}",
        )

    return ScreenResult(
        flagged=False,
        matched_patterns=(),
        reason=None,
    )
