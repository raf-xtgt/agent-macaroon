"""Unit tests for attack catalog templates loader and renderer."""

from red_team.catalog.templates import (
    AttackTemplate,
    TemplateStep,
    load_all_templates,
    render_step,
)


def test_load_all_templates_returns_six() -> None:
    """Assert all 6 YAML templates are loaded correctly."""
    templates = load_all_templates()
    assert isinstance(templates, dict)
    assert len(templates) == 6

    expected_ids = {
        "exfiltrate_insider_data",
        "fabricate_compliance",
        "lateral_jurisdiction",
        "scope_escalation",
        "data_poisoning",
        "defense_evasion",
    }
    assert set(templates.keys()) == expected_ids


def test_template_has_required_fields() -> None:
    """Assert each template conforms to the AttackTemplate schema."""
    templates = load_all_templates()
    for tmpl_id, tmpl in templates.items():
        assert isinstance(tmpl, AttackTemplate)
        assert tmpl.id == tmpl_id
        assert isinstance(tmpl.name, str) and len(tmpl.name) > 0
        assert isinstance(tmpl.description, str) and len(tmpl.description) > 0
        assert isinstance(tmpl.target_layers, list) and len(tmpl.target_layers) > 0
        assert isinstance(tmpl.surfaces, list) and len(tmpl.surfaces) > 0
        assert isinstance(tmpl.techniques, list) and len(tmpl.techniques) > 0
        assert isinstance(tmpl.steps, list) and len(tmpl.steps) > 0
        for step in tmpl.steps:
            assert isinstance(step, TemplateStep)
            assert step.phase in {"probe", "exploit", "pivot", "execution"}
            assert isinstance(step.template, str) and len(step.template) > 0


def test_render_step_substitutes_params() -> None:
    """Assert render_step replaces parameter placeholders with provided values."""
    step = TemplateStep(
        phase="exploit",
        action="test_action",
        surface="user_message",
        template="Check {target_company} for filings of {exfil_target}.",
        params={"target_company": ["Acme"], "exfil_target": ["SecretCorp"]},
    )
    rendered = render_step(
        step,
        {"target_company": "Google UK", "exfil_target": "Apple Inc"},
    )
    assert rendered == "Check Google UK for filings of Apple Inc."
