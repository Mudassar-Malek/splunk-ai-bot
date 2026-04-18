"""Tests for the Claude agent tool dispatch logic."""

import pytest
from unittest.mock import MagicMock, patch

from src.claude_agent import SplunkAIAgent


@pytest.fixture
def mock_splunk():
    splunk = MagicMock()
    splunk.run_search.return_value = [{"host": "api-01", "error_count": "153"}]
    splunk.get_indexes.return_value = ["main", "web_logs", "transactions"]
    splunk.get_saved_searches.return_value = [{"name": "High Error Rate", "search": "index=web_logs error | stats count"}]
    return splunk


def test_dispatch_run_splunk_search(mock_splunk):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        agent = SplunkAIAgent(splunk_client=mock_splunk)
        result = agent._dispatch_tool("run_splunk_search", {
            "spl_query": "index=web_logs status=500 | stats count by host",
            "earliest": "-1h",
            "latest": "now",
            "max_results": 100,
        })
    assert result[0]["host"] == "api-01"
    mock_splunk.run_search.assert_called_once()


def test_dispatch_list_indexes(mock_splunk):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        agent = SplunkAIAgent(splunk_client=mock_splunk)
        result = agent._dispatch_tool("list_indexes", {})
    assert "transactions" in result


def test_dispatch_unknown_tool_raises(mock_splunk):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        agent = SplunkAIAgent(splunk_client=mock_splunk)
        with pytest.raises(ValueError, match="Unknown tool"):
            agent._dispatch_tool("nonexistent_tool", {})


def test_reset_clears_conversation(mock_splunk):
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        agent = SplunkAIAgent(splunk_client=mock_splunk)
        agent.conversation = [{"role": "user", "content": "test"}]
        agent.reset()
        assert agent.conversation == []
