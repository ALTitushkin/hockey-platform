import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from news import event_registry, fact_packet, publish, stories


class DraftPickTradeTest(TestCase):
    def test_trade_requires_linked_identity_and_exact_completed_terms(self):
        pid = 8484136
        lead = ("Max Sasson was traded to the New York Rangers by the Vancouver Canucks on Friday "
                "for a fourth-round pick in the 2029 NHL Draft.")
        story = stories.Story("example", "sasson-trade", "Sasson traded to Rangers", "",
                              datetime(2026, 11, 21, 1, tzinfo=timezone.utc), "trade",
                              {pid}, {"VAN", "NYR"}, True, text=lead, en={pid: "Max Sasson"})
        names = {str(pid): {"ru": "Макс Сассон"}}
        teams = {"NYR": "Рейнджерс", "VAN": "Ванкувер"}
        packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(packet)
        self.assertEqual(packet["claims"][0]["date"], "2026-11-20")
        self.assertTrue(event_registry.complete(fact_packet.revision(packet)))
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story), fact_packet.render(packet)), [])
        source = fact_packet.snapshot(story)
        day = "2026-11-21"
        caption = fact_packet.caption(packet, source, day)
        event = fact_packet.revision(packet)
        data = {"source_snapshot": source, "fact_packet": packet, "packet_hash": fact_packet.key(packet),
                "event_revision": event, "expires_at": fact_packet.expires_at(packet), "auto": True}
        with TemporaryDirectory() as directory, patch.object(publish, "OUT", Path(directory)), \
                patch("news.editorial_lifecycle.utcnow", return_value=story.date), \
                patch("news.editorial_queue.datetime", wraps=datetime, **{"now.return_value": story.date}), \
                patch.object(publish, "channel_key", return_value="tg:-100123456"), \
                patch.object(publish, "tg_send", return_value=(True, "message_id 101")) as send:
            path = publish.save_draft(day, caption, [], "fact", kind="story-a", data=data)
            self.assertTrue(publish.publish(day, ["tg"], kind="story-a", automatic=True)[0])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["messages"]["tg"], [101])
            publish.save_draft(day, caption, [], "fact", kind="story-b", data=data)
            self.assertFalse(publish.publish(day, ["tg"], kind="story-b", automatic=True)[0])
            send.assert_called_once()
            with self.subTest("conflicting consideration"):
                registry = event_registry.Registry(Path(directory) / "event_registry.sqlite3")
                try:
                    conflict = {**event, "facts": {**event["facts"], "round": 3}}
                    self.assertEqual(registry.classify(conflict)["status"], "review")
                finally:
                    registry.close()
        story.text = lead.replace("a fourth-round", "a conditional fourth-round")
        self.assertIsNone(fact_packet.extract(story, names, teams, stories.TEAM_EN))
