from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.config import Settings


logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def generate(self, prompt: str) -> str:
        if not self.available():
            logger.warning("Gemini request skipped because GEMINI_API_KEY is not configured")
            return ""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent?key={self.settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7, "topP": 0.9},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Gemini HTTP error status=%s body=%s", exc.code, body[:2000])
            return ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            logger.exception("Gemini request failed")
            return ""

        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            logger.warning("Gemini response contained no text. Response keys=%s", sorted(data.keys()))
        return text
