"""Контракт headless-пересказа: секреты, повторные попытки и учёт расхода."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news import codex_provider as c
from news import publish


def output(text="Готово"):
    return "\n".join(json.dumps(e) for e in [
        {"type": "error", "message": "Reconnecting"},
        {"type": "item.completed", "item": {"type": "error", "message": "transport fallback"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}}])


class CodexTests(unittest.TestCase):
    def test_oversized_prompt_does_not_launch_cli(self):
        with patch.object(c.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "20000"):
                c.generate("x" * 20001)
            run.assert_not_called()

    def test_recovered_transport_warning_is_not_failed_generation(self):
        self.assertEqual(c.parse_output(output())[0], "Готово")

    def test_incomplete_or_tool_using_turn_is_rejected(self):
        tool = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
        self.assertIsNone(c.parse_output(tool + "\n" + output())[0])
        self.assertIsNone(c.parse_output(json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": "partial"}}))[0])

    def test_secrets_not_inherited_and_usage_has_no_post_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.dict("os.environ", {"NEWS_CODEX_BIN": "codex", "NEWS_BOT_TOKEN": "private",
                                         "OPENAI_API_KEY": "private", "CODEX_HOME": tmp}), \
                patch.object(c.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output())) as run:
            self.assertEqual(c.generate("private post text"), "Готово")
            env = run.call_args.kwargs["env"]
            self.assertNotIn("NEWS_BOT_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertEqual(env["CODEX_HOME"], tmp)
            state = c.read_state()
            self.assertEqual(state["runs"][0]["usage"]["input_tokens"], 100)
            self.assertNotIn("private post text", c.state_path().read_text())

    def test_failure_cools_down_all_news_not_just_one_story(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.dict("os.environ", {"NEWS_CODEX_BIN": "codex"}), \
                patch.object(c.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 120)) as run:
            self.assertIsNone(c.generate("first"))
            self.assertIsNone(c.generate("second"))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(c.read_state()["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
