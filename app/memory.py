from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversationTurn:
    user: str
    assistant: str


class JsonConversationMemory:
    def __init__(self, memory_dir: Path, window: int = 5) -> None:
        self.memory_dir = memory_dir
        self.window = window
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"_", "-"}) or "default"
        return self.memory_dir / f"{safe_id}.json"

    def load(self, session_id: str) -> list[ConversationTurn]:
        path = self._path(session_id)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            turns = [
                ConversationTurn(user=str(item.get("user", "")), assistant=str(item.get("assistant", "")))
                for item in raw
                if isinstance(item, dict)
            ]
            return turns[-self.window :]
        except (json.JSONDecodeError, OSError):
            return []

    def save_turn(self, session_id: str, user: str, assistant: str) -> None:
        turns = self.load(session_id)
        turns.append(ConversationTurn(user=user, assistant=assistant))
        pruned = turns[-self.window :]
        self._path(session_id).write_text(
            json.dumps([asdict(turn) for turn in pruned], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def format(self, session_id: str) -> str:
        lines: list[str] = []
        for turn in self.load(session_id):
            lines.append(f"User: {turn.user}\nAssistant: {turn.assistant}")
        return "\n\n".join(lines)
