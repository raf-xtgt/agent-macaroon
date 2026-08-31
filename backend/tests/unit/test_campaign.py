"""Unit tests for Campaign state machine and multi-step execution."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from audit.trace import Span
from red_team.executor import execute_campaign
from red_team.objectives import OBJECTIVES
from red_team.recon.fleet_map import FleetMap
from red_team.strategy.campaign import Campaign, CampaignState, CampaignStep, StepResult
from red_team.strategy.strategist import CampaignPlan, PlannedStep


def test_campaign_lifecycle_transitions() -> None:
    """Assert Campaign transitions through planning, executing, and complete states."""
    fleet_map = FleetMap(agents={}, ceilings={}, tool_actions={})
    campaign = Campaign(
        id="c-lifecycle-test",
        objective="exfiltrate_insider_data",
        fleet_map=fleet_map,
        max_steps=2,
    )

    assert campaign.status == CampaignState.PLANNING.value

    step1 = CampaignStep(
        step_number=1,
        phase="probe",
        objective="exfiltrate_insider_data",
        surface="user_message",
        payload="Probe step",
    )
    result1 = StepResult(
        step=step1,
        verdict="blocked",
        denial_reasons=["blocked"],
    )
    campaign.add_step_result(result1)
    assert campaign.status == CampaignState.EXECUTING.value

    step2 = CampaignStep(
        step_number=2,
        phase="exploit",
        objective="exfiltrate_insider_data",
        surface="user_message",
        payload="Exploit step",
    )
    result2 = StepResult(
        step=step2,
        verdict="blocked",
        denial_reasons=["blocked"],
    )
    campaign.add_step_result(result2)
    # Hit max_steps (2) -> status must be complete
    assert campaign.status == CampaignState.COMPLETE.value


def test_campaign_early_completion_on_allowed_verdict() -> None:
    """Assert Campaign transitions immediately to complete when a step is allowed."""
    fleet_map = FleetMap(agents={}, ceilings={}, tool_actions={})
    campaign = Campaign(
        id="c-allowed-test",
        objective="exfiltrate_insider_data",
        fleet_map=fleet_map,
        max_steps=5,
    )
    step1 = CampaignStep(
        step_number=1,
        phase="exploit",
        objective="exfiltrate_insider_data",
        surface="user_message",
        payload="Exploit step",
    )
    result1 = StepResult(
        step=step1,
        verdict="allowed",
        denial_reasons=[],
    )
    campaign.add_step_result(result1)
    assert campaign.status == CampaignState.COMPLETE.value


@pytest.mark.asyncio
async def test_execute_campaign_respects_max_steps() -> None:
    """Assert execute_campaign terminates when max_steps limit is reached."""
    objective = OBJECTIVES["exfiltrate_insider_data"]
    root_agent = SimpleNamespace(
        name="root_agent",
        tools=[SimpleNamespace(name="search_companies")],
        sub_agents=[],
    )
    governed_app = SimpleNamespace(
        root_agent=root_agent,
        plugins=[],
    )
    fleet_context = {
        "agent_names": ["root_agent"],
        "tool_names": ["search_companies"],
        "tool_action_map": {"search_companies": "search"},
        "root_agent": root_agent,
    }

    mock_plan = CampaignPlan(
        objective="exfiltrate_insider_data",
        steps=[
            PlannedStep(
                phase="probe",
                surface="user_message",
                target_agent="root_agent",
                technique="instruction_override",
                payload_template="Step 1 payload",
            ),
            PlannedStep(
                phase="exploit",
                surface="user_message",
                target_agent="root_agent",
                technique="instruction_override",
                payload_template="Step 2 payload",
            ),
            PlannedStep(
                phase="exploit",
                surface="user_message",
                target_agent="root_agent",
                technique="instruction_override",
                payload_template="Step 3 payload",
            ),
        ],
    )

    mock_spans = [
        Span(
            span_id="s1",
            parent_span_id=None,
            chain_id="chain-test",
            agent_id="root_agent",
            macaroon_identifier_hash="hash-1",
            action_requested="search_companies",
            decision="deny",
            reason="denied",
            timestamp=datetime.now(timezone.utc),
        )
    ]

    with (
        patch("red_team.executor.plan_campaign", return_value=mock_plan),
        patch("red_team.executor.get_chain_spans", return_value=mock_spans),
        patch("red_team.executor.InMemoryRunner") as mock_runner_cls,
        patch("red_team.executor.App") as mock_app_cls,
    ):
        mock_app_cls.return_value = SimpleNamespace(
            root_agent=root_agent, plugins=[], name="red_team_campaign"
        )
        mock_runner = MagicMock()
        mock_runner.session_service.create_session = AsyncMock()

        async def _mock_run_async(*args: Any, **kwargs: Any) -> Any:
            if False:
                yield None

        mock_runner.run_async = _mock_run_async
        mock_runner_cls.return_value = mock_runner

        campaign = await execute_campaign(
            objective=objective,
            governed_app=governed_app,  # type: ignore[arg-type]
            fleet_context=fleet_context,
            max_steps=2,
        )

    assert len(campaign.results) == 2
    assert campaign.status == CampaignState.COMPLETE.value


@pytest.mark.asyncio
async def test_execute_campaign_stops_on_objective_achieved() -> None:
    """Assert execute_campaign stops early when a step succeeds."""
    objective = OBJECTIVES["fabricate_compliance"]
    root_agent = SimpleNamespace(name="root_agent", tools=[], sub_agents=[])
    governed_app = SimpleNamespace(root_agent=root_agent, plugins=[])
    fleet_context = {"root_agent": root_agent, "tool_action_map": {}}

    mock_plan = CampaignPlan(
        objective="fabricate_compliance",
        steps=[
            PlannedStep(
                phase="exploit",
                surface="tool_response",
                target_agent="root_agent",
                technique="delimiter_confusion",
                payload_template="Step 1 poison",
            ),
            PlannedStep(
                phase="exploit",
                surface="tool_response",
                target_agent="root_agent",
                technique="delimiter_confusion",
                payload_template="Step 2 poison",
            ),
        ],
    )

    mock_spans = [
        Span(
            span_id="s1",
            parent_span_id=None,
            chain_id="chain-test-allowed",
            agent_id="root_agent",
            macaroon_identifier_hash="hash-1",
            action_requested="issue_macaroon",
            decision="allow",
            reason="allowed",
            timestamp=datetime.now(timezone.utc),
        )
    ]

    with (
        patch("red_team.executor.plan_campaign", return_value=mock_plan),
        patch("red_team.executor.get_chain_spans", return_value=mock_spans),
        patch("red_team.executor.InMemoryRunner") as mock_runner_cls,
        patch("red_team.executor.App") as mock_app_cls,
    ):
        mock_app_cls.return_value = SimpleNamespace(
            root_agent=root_agent, plugins=[], name="red_team_campaign"
        )
        mock_runner = MagicMock()
        mock_runner.session_service.create_session = AsyncMock()

        async def _mock_run_async(*args: Any, **kwargs: Any) -> Any:
            if False:
                yield None

        mock_runner.run_async = _mock_run_async
        mock_runner_cls.return_value = mock_runner

        campaign = await execute_campaign(
            objective=objective,
            governed_app=governed_app,  # type: ignore[arg-type]
            fleet_context=fleet_context,
            max_steps=5,
        )

    # Should have stopped after step 1 because verdict was allowed
    assert len(campaign.results) == 1
    assert campaign.results[0].verdict == "allowed"
    assert campaign.status == CampaignState.COMPLETE.value


@pytest.mark.asyncio
async def test_execute_campaign_creates_runner_with_poison_plugin_per_step() -> None:
    """Assert execute_campaign creates App with PoisonPlugin at position 0 on tool_response steps."""
    from red_team.poison_plugin import PoisonPlugin

    objective = OBJECTIVES["fabricate_compliance"]
    root_agent = SimpleNamespace(
        name="root_agent",
        tools=[SimpleNamespace(name="get_company_profile")],
        sub_agents=[],
    )
    governed_app = SimpleNamespace(root_agent=root_agent, plugins=[])
    fleet_context = {
        "root_agent": root_agent,
        "tool_action_map": {"get_company_profile": "read"},
    }

    mock_plan = CampaignPlan(
        objective="fabricate_compliance",
        steps=[
            PlannedStep(
                phase="exploit",
                surface="tool_response",
                target_agent="root_agent",
                target_tool="get_company_profile",
                technique="context_manipulation",
                payload_template="Poisoned compliance notes",
            )
        ],
    )

    created_apps = []

    def _mock_app_init(*args: Any, **kwargs: Any) -> Any:
        app_obj = SimpleNamespace(
            root_agent=kwargs.get("root_agent"),
            plugins=kwargs.get("plugins", []),
            name=kwargs.get("name"),
        )
        created_apps.append(app_obj)
        return app_obj

    with (
        patch("red_team.executor.plan_campaign", return_value=mock_plan),
        patch("red_team.executor.get_chain_spans", return_value=[]),
        patch("red_team.executor.InMemoryRunner") as mock_runner_cls,
        patch("red_team.executor.App", side_effect=_mock_app_init),
    ):
        mock_runner = MagicMock()
        mock_runner.session_service.create_session = AsyncMock()

        async def _mock_run_async(*args: Any, **kwargs: Any) -> Any:
            if False:
                yield None

        mock_runner.run_async = _mock_run_async
        mock_runner_cls.return_value = mock_runner

        await execute_campaign(
            objective=objective,
            governed_app=governed_app,  # type: ignore[arg-type]
            fleet_context=fleet_context,
            max_steps=1,
        )

    assert len(created_apps) == 1
    step_app = created_apps[0]
    assert len(step_app.plugins) == 1
    assert isinstance(step_app.plugins[0], PoisonPlugin)
    assert step_app.plugins[0]._target_tool == "get_company_profile"
