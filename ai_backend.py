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
    filename="ai_backend.log",
    filemode="a",  # 'a' appends new logs; 'w' overwrites the file each run
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M %d %B",
    encoding="utf-8",
)

# 3. Log a standard informational message
logger.info("The application started successfully.")

# ============================================================================================
#                                       TOOL DEFINITIONS
# ============================================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
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
                "required": ["query", "num_results"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]

# ================================================================================================
#                                   TOOL EXECUTOR
# ==============================================================================================
# ----------------------------------------------------------------------------------------------
# Register all available tools here
# -------------------------------------------------------------------------------------------------

from typing import Callable
from tools import web_search

AVAILABLE_TOOLS: dict[str, Callable] = {
    "web_search": web_search,
}


# ------------------------------------------------------------------
# Executes tool calls returned by the LLM
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


# ============================================================================================
from typing import Optional, Literal
from pydantic import BaseModel


class Thought(BaseModel):
    goal: str
    reasoning: str
    confidence: float


class NextAction(BaseModel):
    type: Literal["tool", "respond", "finish"]
    tool_name: Optional[str] = None
    tool_call_id: str = None
    arguments: Optional[dict] = None


class Observation(BaseModel):
    tool_call_id: str = None
    tool_name: str = None
    success: Optional[bool] = None
    summary: Optional[str] = None
    confidence: Optional[float] = None
    data: Optional[dict] = None


class AgentState(BaseModel):
    stage: Literal["THINK", "OBSERVE", "FINAL"]
    thought: Thought
    next_action: NextAction
    observation: Observation
    final_answer: Optional[str] = None


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

    system_prompt = """You are a helpful ReAct (Reasoning + Acting) Agent.

Stage 1:
Decide whether you can answer directly or require tool calls.

Stage 2:
Observe tool results.
If sufficient, answer.
Otherwise continue reasoning and call more tools.

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
            top_p=0.7,
            max_tokens=1024,
            reasoning_effort="low",
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
