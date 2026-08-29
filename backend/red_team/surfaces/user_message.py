"""User message injection surface preparation."""

from typing import Any


def prepare_user_message_surface(payload: str, **kwargs: Any) -> dict[str, Any]:
    """Prepare execution parameters for direct user prompt injection.

    Args:
        payload: Adversarial prompt text.
        **kwargs: Additional parameters.

    Returns:
        dict[str, Any]: Configuration dictionary for the executor.
    """
    return {
        "surface": "user_message",
        "message_text": payload,
        "plugin": None,
    }
