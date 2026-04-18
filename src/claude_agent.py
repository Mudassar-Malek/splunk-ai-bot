"""
Claude-powered agent: natural language → SPL → execute → synthesise results.
All configurable values come from config.yaml or environment variables.
"""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
import yaml

from .splunk_client import SplunkClient

# Load config — allows non-secret settings to be changed without code edits
_config_path = Path(__file__).parent.parent / "config.yaml"
_config: dict = yaml.safe_load(_config_path.read_text()) if _config_path.exists() else {}

SYSTEM_PROMPT = """You are SplunkBot, an expert Splunk Power User and incident responder.

Your responsibilities:
1. Translate natural-language questions into correct, efficient SPL queries.
2. Analyse Splunk search results and surface actionable insights.
3. Identify anomalies, error spikes, and potential root causes from log data.
4. Suggest follow-up searches when the first result is inconclusive.

SPL Guidelines:
- Always scope searches with `index=` and a time range.
- Prefer `stats count by` over raw event dumps for large result sets.
- Never use wildcard-only searches (`index=* sourcetype=*`) — they are expensive.
- Add `| head 100` as a safety limit when result size is unknown.

When returning a query wrap it in a ```spl code block.
Lead every answer with the key finding in one sentence.
"""

TOOLS = [
    {
        "name": "run_splunk_search",
        "description": "Execute an SPL query against Splunk and return raw results as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spl_query": {
                    "type": "string",
                    "description": "Valid SPL search string (without leading 'search' keyword).",
                },
                "earliest": {
                    "type": "string",
                    "description": "Splunk time modifier for start of window e.g. '-1h', '-24h@d'.",
                    "default": _config.get("default_time_window", {}).get("earliest", "-15m"),
                },
                "latest": {
                    "type": "string",
                    "description": "Splunk time modifier for end of window.",
                    "default": _config.get("default_time_window", {}).get("latest", "now"),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum events to return.",
                    "default": _config.get("max_results", 500),
                },
            },
            "required": ["spl_query"],
        },
    },
    {
        "name": "list_indexes",
        "description": "Return available Splunk indexes so the agent can pick the right one.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_saved_searches",
        "description": "Return saved Splunk searches (alerts/reports) relevant to the question.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


class SplunkAIAgent:
    def __init__(self, splunk_client: SplunkClient, model: str | None = None):
        self.splunk = splunk_client
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model or _config.get("claude_model", "claude-sonnet-4-6")
        self.max_tokens = _config.get("max_tokens", 4096)
        self.conversation: list[dict] = []

    def chat(self, user_message: str) -> str:
        self.conversation.append({"role": "user", "content": user_message})
        return self._agentic_loop()

    def _agentic_loop(self) -> str:
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.conversation,
            )

            text = ""
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    text = block.text
                elif block.type == "tool_use":
                    tool_uses.append(block)

            self.conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn" or not tool_uses:
                return text

            tool_results = []
            for tu in tool_uses:
                result = self._dispatch_tool(tu.name, tu.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, default=str),
                })
            self.conversation.append({"role": "user", "content": tool_results})

    def _dispatch_tool(self, name: str, inputs: dict) -> Any:
        defaults = _config.get("default_time_window", {})
        if name == "run_splunk_search":
            return self.splunk.run_search(
                spl_query=inputs["spl_query"],
                earliest=inputs.get("earliest", defaults.get("earliest", "-15m")),
                latest=inputs.get("latest", defaults.get("latest", "now")),
                max_results=inputs.get("max_results", _config.get("max_results", 500)),
            )
        if name == "list_indexes":
            excluded = set(_config.get("excluded_indexes", []))
            return [i for i in self.splunk.get_indexes() if i not in excluded]
        if name == "list_saved_searches":
            return self.splunk.get_saved_searches()
        raise ValueError(f"Unknown tool: {name}")

    def reset(self) -> None:
        self.conversation = []
