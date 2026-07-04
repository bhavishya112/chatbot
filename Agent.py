from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.agent import ProductionAgent
from app.config import Settings
from app.logging_config import configure_logging
from app.schemas import AgentRequest


logger = logging.getLogger(__name__)


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    configure_logging()
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        request = AgentRequest.from_dict(data)
        settings = Settings.from_env()
        logger.info(
            "Starting agent request session_id=%s query_chars=%s local_model_url=%s local_model_name=%s",
            request.session_id,
            len(request.query),
            settings.local_model_url,
            settings.local_model_name,
        )
        agent = ProductionAgent(settings)

        for event in agent.stream(request):
            emit(event)
        return 0
    except Exception:
        logger.exception("Agent request failed")
        emit({"event": "error", "error": "Sorry, the agent could not complete that request."})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
