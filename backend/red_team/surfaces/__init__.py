"""Injection surface adapters for red-team campaigns."""

from .inter_agent import prepare_inter_agent_surface
from .state_injection import prepare_state_injection_surface
from .tool_response import prepare_tool_response_surface
from .user_message import prepare_user_message_surface

__all__ = [
    "prepare_inter_agent_surface",
    "prepare_state_injection_surface",
    "prepare_tool_response_surface",
    "prepare_user_message_surface",
]
