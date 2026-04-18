"""
Interactive CLI entry point for SplunkBot.
Run: python -m src.cli
"""

import os
import sys
import readline  # noqa: F401 — enables arrow-key history in the REPL

from .splunk_client import SplunkClient
from .claude_agent import SplunkAIAgent


def _require_env(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        print(f"[error] environment variable {var} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def main() -> None:
    splunk = SplunkClient(
        host=_require_env("SPLUNK_HOST"),
        port=int(os.environ.get("SPLUNK_PORT", "8089")),
        username=_require_env("SPLUNK_USERNAME"),
        password=_require_env("SPLUNK_PASSWORD"),
        verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() != "false",
    )

    agent = SplunkAIAgent(splunk_client=splunk)

    print("SplunkBot  (type 'exit' to quit, 'reset' to clear conversation)\n")
    print("Connected to:", os.environ["SPLUNK_HOST"])
    print("-" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye.")
            break
        if user_input.lower() == "reset":
            agent.reset()
            print("[conversation cleared]")
            continue

        print("\nSplunkBot: ", end="", flush=True)
        try:
            reply = agent.chat(user_input)
            print(reply)
        except Exception as exc:
            print(f"\n[error] {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
