"""Unit tests for red-team attack objectives validation."""

from red_team.objectives import OBJECTIVES, AttackObjective


def test_objectives_count_and_keys() -> None:
    """Assert all 5 required attack objectives are present and keyed by id."""
    expected_ids = {
        "exfiltrate_insider_data",
        "fabricate_compliance",
        "lateral_jurisdiction",
        "scope_escalation",
        "data_poisoning",
    }
    assert set(OBJECTIVES.keys()) == expected_ids
    assert len(OBJECTIVES) == 5


def test_objectives_fields_non_empty() -> None:
    """Assert all objective dataclasses contain valid, non-empty fields."""
    for obj_id, obj in OBJECTIVES.items():
        assert isinstance(obj, AttackObjective)
        assert obj.id == obj_id
        assert isinstance(obj.name, str) and len(obj.name.strip()) > 0
        assert isinstance(obj.description, str) and len(obj.description.strip()) > 0
        assert isinstance(obj.example_goal, str) and len(obj.example_goal.strip()) > 0
        assert isinstance(obj.target_tools, list) and len(obj.target_tools) > 0
        assert all(isinstance(t, str) and len(t) > 0 for t in obj.target_tools)


def test_objectives_injection_surface_valid() -> None:
    """Assert injection_surface is strictly either 'user_message' or 'tool_response'."""
    valid_surfaces = {"user_message", "tool_response"}
    for obj in OBJECTIVES.values():
        assert (
            obj.injection_surface in valid_surfaces
        ), f"Objective {obj.id} has invalid surface: {obj.injection_surface}"


def test_objectives_surface_distribution() -> None:
    """Assert presence of both user_message (Surface A) and tool_response (Surface B) objectives."""
    surfaces = {obj.injection_surface for obj in OBJECTIVES.values()}
    assert "user_message" in surfaces
    assert "tool_response" in surfaces
