"""Unit tests for SplunkClient — all HTTP calls are mocked."""

import pytest
import responses

from src.splunk_client import SplunkClient

BASE = "https://splunk.example.com:8089"


@pytest.fixture
def client():
    return SplunkClient("splunk.example.com", 8089, "admin", "secret", verify_ssl=False)


@responses.activate
def test_run_search_returns_results(client):
    responses.add(responses.POST, f"{BASE}/services/search/jobs",
                  json={"sid": "test_sid_123"}, status=201)
    responses.add(responses.GET, f"{BASE}/services/search/jobs/test_sid_123",
                  json={"entry": [{"content": {"dispatchState": "DONE"}}]}, status=200)
    responses.add(responses.GET, f"{BASE}/services/search/jobs/test_sid_123/results",
                  json={"results": [{"host": "web-01", "count": "42"}]}, status=200)

    results = client.run_search("index=web_logs | stats count by host")
    assert len(results) == 1
    assert results[0]["host"] == "web-01"


@responses.activate
def test_get_indexes(client):
    responses.add(responses.GET, f"{BASE}/services/data/indexes",
                  json={"entry": [{"name": "main"}, {"name": "web_logs"}]}, status=200)

    indexes = client.get_indexes()
    assert "main" in indexes
    assert "web_logs" in indexes


@responses.activate
def test_job_timeout_raises(client):
    responses.add(responses.POST, f"{BASE}/services/search/jobs",
                  json={"sid": "slow_sid"}, status=201)
    # Always return RUNNING to trigger timeout
    for _ in range(100):
        responses.add(responses.GET, f"{BASE}/services/search/jobs/slow_sid",
                      json={"entry": [{"content": {"dispatchState": "RUNNING"}}]}, status=200)

    with pytest.raises(TimeoutError):
        client._wait_for_job("slow_sid", timeout=1, poll_interval=0.1)
