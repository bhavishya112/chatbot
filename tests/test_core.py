import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.memory import JsonConversationMemory
from app.schemas import ToolRequest
from app.tools.registry import ToolRegistry
from app.tools.ui_resolution import UIResolutionTool


class CoreTests(unittest.TestCase):
    def test_memory_prunes_to_window(self) -> None:
        with TemporaryDirectory() as directory:
            memory = JsonConversationMemory(Path(directory), window=5)
            for index in range(7):
                memory.save_turn("session", f"u{index}", f"a{index}")
            turns = memory.load("session")
            self.assertEqual(len(turns), 5)
            self.assertEqual(turns[0].user, "u2")
            self.assertEqual(turns[-1].assistant, "a6")

    def test_tool_registry_executes_registered_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(UIResolutionTool())
        result = registry.execute(
            "ui_resolution",
            {
                "question": "why is send broken",
                "visible_html": "<button id='sendBtn'>Send</button>",
                "console_errors": [],
            },
            "session",
        )
        self.assertTrue(result.ok)
        self.assertIn("sendBtn", result.content)

    def test_ui_resolution_rejects_empty_context(self) -> None:
        tool = UIResolutionTool()
        result = tool.execute(
            ToolRequest(
                name="ui_resolution",
                arguments={"question": "what is on screen", "visible_html": "", "console_errors": []},
                session_id="session",
            )
        )
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
