"""Smoke tests for the 3-agent delegation chain structure and wiring."""

from agents.orchestrator.agent import orchestrator_agent, root_agent
from agents.researcher.agent import fetch_document, researcher_agent
from agents.tool_caller.agent import delete_record, read_record, tool_caller_agent


def test_agent_chain_structure() -> None:
    """Assert the 3-agent hierarchy and tool registrations are correctly wired."""
    # Test root_agent export
    assert root_agent is orchestrator_agent

    # Test orchestrator delegation
    assert orchestrator_agent.name == "orchestrator_agent"
    assert orchestrator_agent.sub_agents is not None
    assert researcher_agent in orchestrator_agent.sub_agents

    # Test researcher delegation and tools
    assert researcher_agent.name == "researcher_agent"
    assert researcher_agent.sub_agents is not None
    assert tool_caller_agent in researcher_agent.sub_agents
    assert researcher_agent.tools is not None
    assert fetch_document in researcher_agent.tools

    # Test tool_caller leaf agent tools and absence of sub-agents
    assert tool_caller_agent.name == "tool_caller_agent"
    assert tool_caller_agent.tools is not None
    assert read_record in tool_caller_agent.tools
    assert delete_record in tool_caller_agent.tools
    assert not tool_caller_agent.sub_agents


def test_mock_tool_signatures_and_returns() -> None:
    """Assert tool functions return expected dictionary structures."""
    read_res = read_record(record_id="rec-123")
    assert read_res == {
        "record_id": "rec-123",
        "content": "mock record content",
        "action": "read",
    }

    del_res = delete_record(record_id="rec-123")
    assert del_res == {
        "record_id": "rec-123",
        "status": "deleted",
        "action": "delete",
    }

    doc_res = fetch_document(document_id="doc-456")
    assert doc_res == {
        "document_id": "doc-456",
        "text": "This is a mock document with no injected instructions.",
    }
