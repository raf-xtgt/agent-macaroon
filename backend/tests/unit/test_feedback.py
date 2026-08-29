"""Unit tests for defense feedback parsing."""

from red_team.strategy.campaign import CampaignStep, StepResult
from red_team.strategy.feedback import StrategySignal, parse_defense_response


def test_parse_allowed_verdict() -> None:
    """Assert allowed verdict yields success=True and no defense layer block."""
    step = CampaignStep(
        step_number=1,
        phase="exploit",
        objective="exfiltrate_insider_data",
        surface="user_message",
        payload="Test query",
    )
    result = StepResult(
        step=step,
        verdict="allowed",
        denial_reasons=[],
        defense_layer=None,
    )
    signal = parse_defense_response(result)
    assert isinstance(signal, StrategySignal)
    assert signal.success is True
    assert signal.blocked_by is None
    assert "Objective achieved" in signal.recommendation


def test_parse_f5_model_armor_block() -> None:
    """Assert model armor quarantine denial maps to F5_model_armor and context manipulation recommendation."""
    step = CampaignStep(
        step_number=1,
        phase="exploit",
        objective="fabricate_compliance",
        surface="tool_response",
        payload="Poison text",
    )
    result = StepResult(
        step=step,
        verdict="blocked",
        denial_reasons=["quarantined fields: ['company_name'] by Model Armor"],
        defense_layer="F5_model_armor",
    )
    signal = parse_defense_response(result)
    assert signal.success is False
    assert signal.defense_layer == "F5_model_armor"
    assert signal.blocked_by == "model_armor"
    assert "context manipulation" in signal.recommendation.lower()


def test_parse_f5_regex_block() -> None:
    """Assert static screen regex denial maps to F5_regex and encoding evasion recommendation."""
    step = CampaignStep(
        step_number=1,
        phase="exploit",
        objective="scope_escalation",
        surface="user_message",
        payload="Ignore instructions",
    )
    result = StepResult(
        step=step,
        verdict="blocked",
        denial_reasons=["screen:matched static regex pattern #4"],
        defense_layer="F5_regex",
    )
    signal = parse_defense_response(result)
    assert signal.success is False
    assert signal.defense_layer == "F5_regex"
    assert signal.blocked_by == "screen_regex"
    assert "encoding evasion" in signal.recommendation.lower()


def test_parse_f4_gateway_block() -> None:
    """Assert macaroon scope caveat denial maps to F4_gateway and pivot recommendation."""
    step = CampaignStep(
        step_number=1,
        phase="exploit",
        objective="lateral_jurisdiction",
        surface="user_message",
        payload="Cross border search",
    )
    result = StepResult(
        step=step,
        verdict="blocked",
        denial_reasons=["scope caveat violated: action 'retrieve' not permitted"],
        defense_layer="F4_gateway",
    )
    signal = parse_defense_response(result)
    assert signal.success is False
    assert signal.defense_layer == "F4_gateway"
    assert signal.blocked_by == "gateway_scope"
    assert "broader scope ceiling" in signal.recommendation.lower()
