"""
Claude-powered agent that translates natural language questions into SPL,
executes them, and synthesises the results into human-readable answers.
"""

import json
import os
from typing import Any

import anthropic

from .splunk_client import SplunkClient

SYSTEM_PROMPT = """You are SplunkBot, an expert Splunk Power User and incident responder embedded in a fintech SRE team.

Your responsibilities:
1. Translate natural-language questions into correct, efficient SPL queries.
2. Analyse Splunk search results and surface actionable insights.
3. Identify anomalies, error spikes, and potential root causes from log data.
4. Suggest follow-up searches when the first result is inconclusive.

SPL Guidelines you must follow:
- Always scope searches with `index=` and a time range.
- Prefer `stats count by` over raw event dumps for large result sets.
- Use `eval` and `rex` for field extraction when needed.
- Never use wildcard-only searches (`index=* sourcetype=*`) — they are expensive.
- Add `| head 100` as a safety limit when result size is unknown.

When returning a query, wrap it in a ```spl code block.
When summarising results, lead with the key finding in one sentence, then detail.
"""

TOOLS = [
    {
        "name": "run_splunk_search",
        "description": "Execute an SPL query against Splunk and return raw results as a JSON array.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spl_query": {
                    "type": "string",
                    "description": "A valid SPL search string (without leading 'search' keyword).",
                },
                "earliest": {
                    "type": "string",
                    "description": "Splunk time modifier for start of window, e.g. '-1h', '-24h@d'.",
                    "default": "-15m",
                },
                "latest": {
                    "type": "string",
                    "description": "Splunk time modifier for end of window.",
                    "default": "now",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return.",
                    "default": 500,
                },
            },
            "required": ["spl_query"],
        },
    },
    {
        "name": "list_indexes",
        "description": "Return the list of available Splunk indexes so the agent can pick the right one.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_saved_searches",
        "description": "Return saved Splunk searches (alerts and reports) that may be relevant to the user's question.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


class SplunkAIAgent:
    def __init__(self, splunk_client: SplunkClient, model: str = "claude-sonnet-4-6"):
        self.splunk = splunk_client
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.conversation: list[dict] = []

    def chat(self, user_message: str) -> str:
        self.conversation.append({"role": "user", "content": user_message})
        return self._agentic_loop()

    def _agentic_loop(self) -> str:
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.conversation,
            )

            # Collect any text content first
            assistant_text = ""
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    assistant_text = block.text
                elif block.type == "tool_use":
                    tool_uses.append(block)

            self.conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn" or not tool_uses:
                return assistant_text

            # Execute tools and feed results back
            tool_results = []
            for tool_use in tool_uses:
                result = self._dispatch_tool(tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result, default=str),
                })

            self.conversation.append({"role": "user", "content": tool_results})

    def _dispatch_tool(self, name: str, inputs: dict) -> Any:
        if name == "run_splunk_search":
            return self.splunk.run_search(
                spl_query=inputs["spl_query"],
                earliest=inputs.get("earliest", "-15m"),
                latest=inputs.get("latest", "now"),
                max_results=inputs.get("max_results", 500),
            )
        if name == "list_indexes":
            return self.splunk.get_indexes()
        if name == "list_saved_searches":
            return self.splunk.get_saved_searches()
        raise ValueError(f"Unknown tool: {name}")

    def reset(self) -> None:
        self.conversation = []
