"""
Splunk REST API client — wraps search job lifecycle and result pagination.
"""

import time
import requests
from typing import Any
from urllib.parse import urljoin


class SplunkClient:
    def __init__(self, host: str, port: int, username: str, password: str, verify_ssl: bool = True):
        self.base_url = f"https://{host}:{port}"
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.auth = (username, password)

    def run_search(self, spl_query: str, earliest: str = "-15m", latest: str = "now", max_results: int = 1000) -> list[dict]:
        """Submit a search job, poll until done, return results."""
        job_sid = self._create_job(spl_query, earliest, latest)
        self._wait_for_job(job_sid)
        return self._fetch_results(job_sid, max_results)

    def _create_job(self, query: str, earliest: str, latest: str) -> str:
        url = urljoin(self.base_url, "/services/search/jobs")
        payload = {
            "search": query if query.startswith("search ") else f"search {query}",
            "earliest_time": earliest,
            "latest_time": latest,
            "output_mode": "json",
        }
        resp = self.session.post(url, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["sid"]

    def _wait_for_job(self, sid: str, timeout: int = 120, poll_interval: float = 2.0) -> None:
        url = urljoin(self.base_url, f"/services/search/jobs/{sid}")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = self.session.get(url, params={"output_mode": "json"}, timeout=10)
            resp.raise_for_status()
            state = resp.json()["entry"][0]["content"]["dispatchState"]
            if state == "DONE":
                return
            if state in ("FAILED", "ZOMBIE"):
                raise RuntimeError(f"Splunk job {sid} entered state {state}")
            time.sleep(poll_interval)
        raise TimeoutError(f"Splunk job {sid} did not complete within {timeout}s")

    def _fetch_results(self, sid: str, count: int) -> list[dict]:
        url = urljoin(self.base_url, f"/services/search/jobs/{sid}/results")
        resp = self.session.get(url, params={"output_mode": "json", "count": count}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def get_indexes(self) -> list[str]:
        url = urljoin(self.base_url, "/services/data/indexes")
        resp = self.session.get(url, params={"output_mode": "json", "count": 200}, timeout=15)
        resp.raise_for_status()
        return [e["name"] for e in resp.json().get("entry", [])]

    def get_saved_searches(self) -> list[dict]:
        url = urljoin(self.base_url, "/services/saved/searches")
        resp = self.session.get(url, params={"output_mode": "json", "count": 200}, timeout=15)
        resp.raise_for_status()
        return [
            {"name": e["name"], "search": e["content"].get("search", "")}
            for e in resp.json().get("entry", [])
        ]
