"""Offline operator and partial-delivery contracts; no real Telegram/MAX calls."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from news import publish, service


class OperatorQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.patch = patch.object(publish, "OUT", self.out)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_legacy_button_cannot_approve_new_version_without_hash(self):
        publish.save_draft("2026-11-07", "first", [], "review", data={"auto": False})
        publish.save_draft("2026-11-07", "changed", [], "review", data={"auto": False})
        cb = {"callback_query": {"id": "cb", "from": {"id": 42}, "data": "pub:night:2026-11-07",
                                 "message": {"chat": {"id": 42}, "message_id": 1}}}
        with patch.object(publish, "publish") as send:
            service.handle_update(cb, "42", Mock(return_value={"ok": True}))
            send.assert_not_called()

    def test_partial_tg_max_delivery_remains_visible_for_recovery(self):
        publish.save_draft("2026-11-07", "text", [], "template", data={"auto": True})
        with (patch.dict(os.environ, {"MAX_BOT_TOKEN": "test", "MAX_CHAT_ID": "test"}),
              patch.object(publish, "tg_send", return_value=(True, "message_id 50")),
              patch.object(publish, "max_send", return_value=(False, "temporary failure"))):
            ok, _ = publish.publish("2026-11-07", ["tg", "max"])
        self.assertFalse(ok)
        tasks = publish.editorial_pending()
        self.assertIn("2026-11-07_night.json", [task["name"] for task in tasks])


if __name__ == "__main__":
    unittest.main()
