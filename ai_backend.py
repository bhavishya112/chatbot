#!/usr/bin/env python3
import json
import sys
import logging
import traceback

# Force stdout/stderr to use UTF-8 and LF line endings
sys.stdout.reconfigure(encoding="utf-8", newline="\n")
sys.stderr.reconfigure(encoding="utf-8", newline="\n")

# Configure logging
logger = logging.getLogger(__name__)

logging.basicConfig(
    filename="logs/ai_backend.log",
    filemode="a",  # 'a' appends new logs; 'w' overwrites each run
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    datefmt="%H:%M %d %B",
    encoding="utf-8",
)

# 3. Log a standard informational message
logger.info("The application started successfully.")

# ============================================================================================
#                                       TOOL DEFINITIONS | TOOL REGISTRY | TOOLS
# ============================================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the internet for information using Google-like queries. Use only when user wants up-to-date information, not otherwise. Always Preserve URL references with text",
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
                "required": ["query", "num_results"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ui",
            "description": """Gets UI context. Helps with our website navigation. First Ask which device user is on.  Do not add anything by yourself.
            your answer must necessarily be like : 'Go to middle of the page a wide grid of blue boxes would appear' or 'go to profile > settings > notification'
            Remember DO NOT reveal dynamic text like student name or applications ids """,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The UI question e.g. 'leave applications' or 'my content'.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many top matches to get (default 5)",
                    },
                    "view": {
                        "type": "string",
                        "enum": ["mobile", "desktop"],
                        "description": "Which device is user using (default desktop)",
                    },
                    "collection": {
                        "type": "string",
                        "enum": ["ui_elements"],
                        "description": "vectordb collection to use for retrieval",
                    },
                },
                "required": ["question", "top_k", "view", "collection"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]

# ================================================================================================
#                                   TOOL EXECUTOR
# ==============================================================================================
# ----------------------------------------------------------------------------------------------
# Register all available tools here
# -------------------------------------------------------------------------------------------------

from typing import Callable
from tools import web_search, query_ui

AVAILABLE_TOOLS: dict[str, Callable] = {"web_search": web_search, "query_ui": query_ui}


# ------------------------------------------------------------------
# Executes tool calls returned by the LLM (Not to be modified with new tool)
# ------------------------------------------------------------------
def run_tool(tool_name, **args) -> str:
    """
    Executes tool calls

    Returns:
        String representation of Observation
    """
    result = ""
    # Find tool
    tool = AVAILABLE_TOOLS.get(tool_name)

    # Execute tool
    try:
        obs = tool(**args)
    except Exception as e:
        result = f"Tool execution failed: {e}"

    result += f"Tool: {tool_name}\n" f"Arguments: {args}\n" f"Observation:\n{obs}\n"

    return result


# ------------------------------------------------------------------------

# -------------------------------------------------------------------------
# ======================================================================================================================
# ----------------------------------------AGENT--------------------------------------------------------------------------------
# ======================================================================================================================
from openai import OpenAI

# client = OpenAI(
#     base_url="http://localhost:11434/v1",
#     api_key="",
# )
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key="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",
)

MAX_ITERATIONS = 5
MODEL = "openai/gpt-oss-20b"
# MODEL = "llama3.1:8b"


import json
import pprint
import sys


def emit(event: str, data):
    print(f"event: {event}")
    print("data:", json.dumps(data, ensure_ascii=False))
    print()
    sys.stdout.flush()


def Agent(model: str, query: str):

    system_prompt = """
You are helpful chatbot for our ASD Academy
UI information may ONLY come from tool outputs.
IMPORTANT : For ui related queries, provide full information such as size,position,color, flow like myprofile>billing>details

Never answer UI-related questions from your internal knowledge or reasoning. If no tool has returned the requested information, reply that it could not be found instead of guessing.
You are ReAct (Reasoning + Acting) Agent and can help with user navigation and up-to-date information 

Working:
Stage 1:
Decide whether you can answer directly or require tool calls.

Stage 2:
Observe tool results.
If sufficient, answer.
Otherwise continue reasoning and call more tools.

Personality:
Very User Friendly : give your best to help, Factually correct : You do not deviate from provided information


Terminate ONLY by giving a final answer with no tool calls.
"""

    sys_message = [{"role": "system", "content": system_prompt}]
    messages = [{"role": "user", "content": query}]

    round = 0

    for _ in range(MAX_ITERATIONS):

        round += 1

        logger.info(
            "[🐦‍🔥 CONTEXT %d]\n%s",
            round,
            pprint.pformat(messages, width=150),
        )

        stream = client.chat.completions.create(
            model=model,
            messages=sys_message + messages,
            tools=TOOLS,
            temperature=0.2,
            top_p=0.4,
            max_tokens=1024,
            reasoning_effort="medium",
            stream=True,
        )

        assistant_content = ""
        assistant_reasoning = ""

        tool_calls = {}

        finish_reason = None

        for chunk in stream:

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            finish_reason = choice.finish_reason

            # ----------------------------
            # reasoning
            # ----------------------------

            reasoning = getattr(delta, "reasoning", None)

            if reasoning:
                assistant_reasoning += reasoning
                emit("thinking", {"token": reasoning})

            # ----------------------------
            # assistant content
            # ----------------------------

            if delta.content:
                assistant_content += delta.content
                emit("message", {"token": delta.content})

            # ----------------------------
            # tool calls
            # ----------------------------

            if delta.tool_calls:

                for tc in delta.tool_calls:

                    idx = tc.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }

                    if tc.id:
                        tool_calls[idx]["id"] = tc.id

                    if tc.function:

                        if tc.function.name:
                            tool_calls[idx]["name"] = tc.function.name

                        if tc.function.arguments:
                            tool_calls[idx]["arguments"] += tc.function.arguments

        # ============================================================
        # Tool execution
        # ============================================================

        if tool_calls:

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
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

            for tc in tool_calls.values():

                emit(
                    "tool_call",
                    {
                        "name": tc["name"],
                        "arguments": json.loads(tc["arguments"]),
                    },
                )

                args = json.loads(tc["arguments"])

                result = run_tool(tc["name"], **args)

                logger.info("[TOOL] %s", tc["name"])
                logger.info("[RESULT] %s", result)

                emit(
                    "tool_result",
                    {
                        "name": tc["name"],
                        "result": result,
                    },
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

            continue

        # ============================================================
        # Final answer
        # ============================================================

        break

    emit("done", {})


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

        Agent(MODEL, query)
        logger.info("Application Ended Successfully\n\n")

    except Exception as e:
        logger.exception(e)

        print("event: error")
        print("data: " + json.dumps({"error": str(e)}))
        print()
        sys.stdout.flush()


if __name__ == "__main__":
    main()
