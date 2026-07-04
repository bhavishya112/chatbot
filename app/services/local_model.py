from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.config import Settings


logger = logging.getLogger(__name__)


class LocalModelService:
    """Generate responses with a locally running Ollama-compatible model."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.local_model_url and self.settings.local_model_name)

    def generate(self, prompt: str) -> str:
        if not self.available():
            logger.warning("Local model request skipped because LOCAL_MODEL_URL or LOCAL_MODEL_NAME is missing")
            return ""

        payload = {
            "model": self.settings.local_model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }
        request = urllib.request.Request(
            self.settings.local_model_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.local_model_timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Local model HTTP error status=%s body=%s", exc.code, body[:2000])
            return ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            logger.exception("Local model request failed")
            return ""

        text = str(data.get("response") or "").strip()
        if not text:
            logger.warning("Local model response contained no text. Response keys=%s", sorted(data.keys()))
        return text
