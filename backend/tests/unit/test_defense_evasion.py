"""Unit tests for the 6th attack objective: defense_evasion."""

from armor.screen import screen_text
from red_team.catalog.templates import load_template, render_step


def test_immunization_poisoning_template_loads() -> None:
    """Assert defense_evasion template loads with 3 sub-strategies."""
    tmpl = load_template("defense_evasion")
    assert tmpl.id == "defense_evasion"
    assert len(tmpl.steps) == 3

    actions = [s.action for s in tmpl.steps]
    assert "layer_gap_probe" in actions
    assert "immunization_poisoning" in actions
    assert "callback_ordering" in actions


def test_layer_gap_probe_payload_passes_f5_regex() -> None:
    """Assert benign-looking scope violation payload passes static F5 regex screen."""
    tmpl = load_template("defense_evasion")
    probe_step = next(s for s in tmpl.steps if s.action == "layer_gap_probe")

    rendered = render_step(probe_step, {"target_company": "Google UK Limited"})
    result = screen_text(rendered)

    # The payload is formulated to look benign to static regex, evading F5 regex
    assert (
        result.flagged is False
    ), f"Unexpectedly matched static pattern: {result.matched_patterns}"


def test_defense_evasion_surfaces_coverage() -> None:
    """Assert defense_evasion targets multiple injection surfaces."""
    tmpl = load_template("defense_evasion")
    surfaces = {s.surface for s in tmpl.steps}
    assert "user_message" in surfaces
    assert "tool_response" in surfaces
    assert "state_injection" in surfaces
