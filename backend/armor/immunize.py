"""Fleet immunization: learns from blocked attacks to catch similar payloads earlier."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from armor.screen import add_runtime_pattern, get_active_pattern_count
from registry.agents_registry import AgentRegistry

_IMPERATIVE_VERBS = (
    "ignore",
    "override",
    "bypass",
    "execute",
    "call",
    "invoke",
    "delete",
    "retrieve",
    "must",
    "should",
    "now",
    "disregard",
    "exfiltrate",
    "fetch",
    "mark",
    "conclude",
    "state",
    "say",
    "write",
    "reset",
    "grant",
    "adhere",
)

_PHRASE_REGEX = re.compile(
    rf"\b(?:{'|'.join(_IMPERATIVE_VERBS)})\b(?:\s+[A-Za-z0-9_-]+){{1,4}}",
    re.IGNORECASE,
)


_STOP_WORDS = frozenset(
    {
        "and",
        "or",
        "the",
        "to",
        "a",
        "an",
        "with",
        "in",
        "for",
        "of",
        "by",
        "is",
        "are",
        "that",
        "this",
        "your",
    }
)


def _extract_key_phrases(text: str) -> list[str]:
    """Extract distinctive multi-word phrases from attack text for pattern building.

    Looks for imperative instruction patterns that are characteristic of
    injection payloads: "ignore all", "you must", "call the function", etc.
    Returns up to 3 phrases, longest first.

    Args:
        text: Raw text content from the quarantined payload.

    Returns:
        list[str]: Up to 3 unique extracted key phrases sorted by length descending.
    """
    seen: set[str] = set()
    phrases: list[str] = []

    for match in _PHRASE_REGEX.finditer(text):
        chunk = match.group(0)
        raw_words = chunk.strip().split()
        words: list[str] = []
        for w in raw_words:
            cleaned_word = re.sub(r"^[^\w]+|[^\w]+$", "", w)
            if cleaned_word:
                words.append(cleaned_word)

        while len(words) >= 2 and words[-1].lower() in _STOP_WORDS:
            words.pop()

        if len(words) >= 2:
            cleaned = " ".join(words)
            normalized = cleaned.lower()
            if normalized not in seen:
                seen.add(normalized)
                phrases.append(cleaned)

    phrases.sort(key=len, reverse=True)
    return phrases[:3]


def _build_pattern_from_phrases(phrases: list[str]) -> str | None:
    """Build a regex pattern string from extracted key phrases.

    Joins phrases with flexible whitespace matching and returns the compiled
    regex string. Returns None if no usable phrases were found.

    Args:
        phrases: List of extracted imperative phrases.

    Returns:
        str | None: Compiled regex pattern string, or None if phrases list is empty.
    """
    if not phrases:
        return None

    phrase_regexes: list[str] = []
    for phrase in phrases:
        words = phrase.strip().split()
        if not words:
            continue
        escaped_words = [re.escape(word) for word in words]
        phrase_regexes.append(r"\s+".join(escaped_words))

    if not phrase_regexes:
        return None

    if len(phrase_regexes) == 1:
        return phrase_regexes[0]

    return f"(?:{'|'.join(phrase_regexes)})"


def immunize_from_quarantine(
    quarantined_text: str,
    agent_id: str,
    registry: AgentRegistry | None = None,
    tighten_verbs: set[str] | None = None,
) -> dict[str, Any]:
    """Immunize the fleet after a blocked attack.

    Two actions:
    1. Extract a pattern from the quarantined content and register it as a
       runtime screening pattern. Future similar payloads will be caught at
       the Model Armor layer instead of requiring the gateway scope check.
    2. Optionally tighten the offending agent's registry ceiling by removing
       specified verbs.

    Args:
        quarantined_text: The original text that was quarantined (before replacement).
        agent_id: The agent whose tool returned the quarantined content.
        registry: AgentRegistry instance for ceiling tightening. If None, skip tightening.
        tighten_verbs: Set of verbs to remove from the agent's ceiling. If None, skip tightening.

    Returns:
        dict with keys:
            - "pattern_added": bool — whether a new runtime pattern was registered
            - "pattern_name": str | None — name of the registered pattern
            - "ceiling_tightened": bool — whether the ceiling was modified
            - "active_pattern_count": int — total patterns after immunization
    """
    phrases = _extract_key_phrases(quarantined_text)
    pattern = _build_pattern_from_phrases(phrases)

    pattern_added = False
    pattern_name: str | None = None

    if pattern is not None:
        pattern_hash = hashlib.md5(quarantined_text.encode("utf-8")).hexdigest()[:8]
        pattern_name = f"immunized_{pattern_hash}"
        add_runtime_pattern(pattern_name, pattern)
        pattern_added = True

    ceiling_tightened = False
    if registry is not None and tighten_verbs is not None:
        registry.tighten_ceiling(agent_id, tighten_verbs)
        ceiling_tightened = True

    return {
        "pattern_added": pattern_added,
        "pattern_name": pattern_name,
        "ceiling_tightened": ceiling_tightened,
        "active_pattern_count": get_active_pattern_count(),
    }
