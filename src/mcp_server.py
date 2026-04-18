"""
MCP (Model Context Protocol) server exposing SplunkBot tools so any MCP-compatible
host (Claude Desktop, kubectl-ai, etc.) can call them directly.

Requires: pip install mcp
Start:    python -m src.mcp_server
"""

import json
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .splunk_client import SplunkClient

app = Server("splunk-ai-bot")

_splunk: SplunkClient | None = None


def _get_splunk() -> SplunkClient:
    global _splunk
    if _splunk is None:
        _splunk = SplunkClient(
            host=os.environ["SPLUNK_HOST"],
            port=int(os.environ.get("SPLUNK_PORT", "8089")),
            username=os.environ["SPLUNK_USERNAME"],
            password=os.environ["SPLUNK_PASSWORD"],
            verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() != "false",
        )
    return _splunk


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="splunk_search",
            description="Run an SPL query against Splunk and return matching events.",
            inputSchema={
                "type": "object",
                "properties": {
                    "spl_query": {"type": "string", "description": "SPL search string"},
                    "earliest": {"type": "string", "default": "-15m"},
                    "latest": {"type": "string", "default": "now"},
                    "max_results": {"type": "integer", "default": 200},
                },
                "required": ["spl_query"],
            },
        ),
        Tool(
            name="splunk_list_indexes",
            description="List available Splunk indexes.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="splunk_saved_searches",
            description="List saved Splunk searches and alerts.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    splunk = _get_splunk()

    if name == "splunk_search":
        results = splunk.run_search(
            spl_query=arguments["spl_query"],
            earliest=arguments.get("earliest", "-15m"),
            latest=arguments.get("latest", "now"),
            max_results=arguments.get("max_results", 200),
        )
        return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]

    if name == "splunk_list_indexes":
        indexes = splunk.get_indexes()
        return [TextContent(type="text", text=json.dumps(indexes, indent=2))]

    if name == "splunk_saved_searches":
        searches = splunk.get_saved_searches()
        return [TextContent(type="text", text=json.dumps(searches, indent=2))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
