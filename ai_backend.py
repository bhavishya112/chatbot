#!/usr/bin/env python3

import json
import sys
import logging
import traceback
from openai import OpenAI

# Force stdout/stderr to use UTF-8 and LF line endings
sys.stdout.reconfigure(encoding="utf-8", newline="\n")
sys.stderr.reconfigure(encoding="utf-8", newline="\n")

# Configure logging once at the top
logging.basicConfig(
    filename="python_logs.log",  # your log file
    level=logging.ERROR,  # log only errors and above
    format="%(asctime)s [python] %(levelname)s: %(message)s",
)


# Global exception handler
def log_unhandled_exceptions(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Let Ctrl+C exit without logging
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = log_unhandled_exceptions

# ============================================================================================
#                                       TOOLS
# ============================================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Searches the internet for information using Google-like queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string, e.g. 'latest AI news' or 'best laptops 2026'.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of search results to return (default 10).",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }
]

# ============================================================================================
#                                   TOOL EXECUTOR
# ============================================================================================
# ------------------------------------------------------------------
# Register all available tools here
# ------------------------------------------------------------------

from typing import Callable
from tools import google_search

AVAILABLE_TOOLS: dict[str, Callable] = {
    "google_search": google_search,
}


# ------------------------------------------------------------------
# Executes tool calls returned by the LLM
# ------------------------------------------------------------------
def run_tool(tool_calls: dict) -> str:
    """
    Executes one or more tool calls.

    Args:
        tool_calls:
        {
            0: {
                "id": "...",
                "name": "google_search",
                "arguments": "{\"query\":\"python\",\"num_results\":\"5\"}"
            }
        }

    Returns:
        String suitable for appending directly to the LLM scratchpad.
    """

    scratchpad = ""

    for _, tool_call in tool_calls.items():

        tool_id = tool_call.get("id", "")
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", "{}")

        # Parse JSON arguments
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            scratchpad += (
                f"\nTool Call ID: {tool_id}\n"
                f"Tool: {tool_name}\n"
                f"Observation: Invalid JSON arguments.\n"
            )
            continue

        # Find tool
        tool = AVAILABLE_TOOLS.get(tool_name)

        if tool is None:
            scratchpad += (
                f"\nTool Call ID: {tool_id}\n"
                f"Tool: {tool_name}\n"
                f"Observation: Unknown tool.\n"
            )
            continue

        # Execute tool
        try:
            result = tool(**args)
        except Exception as e:
            result = f"Tool execution failed: {e}"

        scratchpad += (
            f"\nTool Call ID: {tool_id}\n"
            f"Tool: {tool_name}\n"
            f"Arguments: {json.dumps(args, ensure_ascii=False)}\n"
            f"Observation:\n{result}\n"
        )

    return scratchpad


# ============================================================================================
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

MAX_ITERATIONS = 5


def Agent(model: str, query: str):
    scratch_pad = ""
    system_prompt = f"""You are a helpful educational institute assistant.
    internally (do not express it) you work in 2 stage ReAct (Reasoning + Acting + Observing) cycles
    where you iterate N times (current limit is : {MAX_ITERATIONS})
    here is how it works : 
    if its something you can answer straight on, you can straight on answer back from stage one, else you proceed further
    stage 1 : Reason + Act -> Here you decide whether you're able to answer, or you need more details or more iterations to proceed
    stage 2 : Observe -> Here you output the results in STUDENT FRIENDLY way
    Generate content to the end user only when you're ready or need more details
    you have access to your personal scratch pad do not share these details with the end user 
    scratch pad : {scratch_pad} """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    for _ in range(MAX_ITERATIONS):

        stream = client.chat.completions.create(
            model="llama3.1:8b",
            messages=messages,
            temperature=0.7,
            stream=True,
            tools=TOOLS,
        )

        assistant_content = ""
        tool_calls = {}

        # Read the ENTIRE stream
        for chunk in stream:

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Collect text
            if delta.content:
                assistant_content += delta.content

                print("event: message")
                print("data:", json.dumps({"token": delta.content}, ensure_ascii=False))
                print()
                sys.stdout.flush()

            # Collect tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:

                    idx = tc.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "name": "", "arguments": ""}

                    if tc.id:
                        tool_calls[idx]["id"] = tc.id

                    if tc.function.name:
                        tool_calls[idx]["name"] = tc.function.name

                    if tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments

        # Finished reading this response

        if tool_calls:

            # Save assistant tool request
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls.values()
                    ],
                }
            )

            # Execute tools
            for tc in tool_calls.values():

                result = run_tool({0: tc})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )

            continue

        # Final answer
        break

    print("event: done")
    print("data: {}")
    print()
    sys.stdout.flush()


def main():
    try:

        query = ""

        if len(sys.argv) > 1:
            query = " ".join(sys.argv[1:])

        elif not sys.stdin.isatty():

            raw = sys.stdin.read().strip()

            if raw:
                try:
                    payload = json.loads(raw)
                    query = payload.get("query", "")
                except json.JSONDecodeError:
                    query = raw

        else:
            query = input("Ask something: ").strip()

        if not query:
            print("event: error")
            print("data: " + json.dumps({"error": "Query required"}))
            print()
            sys.stdout.flush()
            return

        Agent("llama3.1:8b", query)

    except Exception as e:

        logging.exception(e)

        print("event: error")
        print("data: " + json.dumps({"error": str(e)}))
        print()
        sys.stdout.flush()


if __name__ == "__main__":
    main()
