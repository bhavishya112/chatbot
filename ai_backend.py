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

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)


def Agent(model: str, query: str):
    client.chat.completions.parse
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful ecommerce assistant."},
            {"role": "user", "content": query},
        ],
        temperature=0.7,
        stream=True,
    )

    for chunk in stream:

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta.content

        if delta:
            print("event: message")
            print("data: " + json.dumps({"token": delta}, ensure_ascii=False))
            print()
            sys.stdout.flush()

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
