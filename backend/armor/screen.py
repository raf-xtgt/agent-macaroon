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
}


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
