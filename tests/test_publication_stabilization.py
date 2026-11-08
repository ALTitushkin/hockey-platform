"""Incident 08.11: useful auto path, opponent logo and repeated source observations."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import editorial_lifecycle, editorial_queue, fact_packet, publish, source_watch, stories, story_provenance


class Stabilization(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 8, tzinfo=timezone.utc)
        self.story = stories.Story(
            "incident", "oilers-injury", "Nugent-Hopkins leaves game for Oilers", "", self.now,
            "injury_minor", {8476454}, {"EDM"}, True,
            text=("Ryan Nugent-Hopkins sustained an apparent head injury in a win for the Edmonton Oilers "
                  "against the Vancouver Canucks on Saturday and did not return to the game.\n\n"
                  "He missed the first nine games of the season with a lower-body injury."),
            en={8476454: "Ryan Nugent Hopkins"}, mentioned={8476454})
        self.names = {"8476454": {"ru": "Райан Ньюджент-Хопкинс", "surname": "Ньюджент-Хопкинс"}}
        self.teams = {"EDM": "Эдмонтон", "VAN": "Ванкувер"}

    def packet(self):
        return fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN)

    def test_incident08_injury_has_verified_template_and_action_date(self):
        p = self.packet()
        self.assertIsNotNone(p)
        self.assertEqual(p["claims"][0]["kind"], "left_game")
        self.assertEqual(p["claims"][0]["date"], "2026-11-07")
        self.assertEqual(fact_packet.verify(p, fact_packet.snapshot(self.story), fact_packet.render(p)), [])
        self.assertIn("7 ноября", fact_packet.render(p))
        self.assertNotIn("нижней", fact_packet.render(p))

    def test_incident08_opponent_in_prose_never_becomes_hero_club(self):
        with patch.object(stories, "render_story_card", return_value=Path("card.png")) as draw:
            stories.card(self.story, "Ньюджент-Хопкинс покинул матч\n\nМатч с Ванкувером.",
                         self.names, set(), [], self.teams, "2026-11-08", Path("card.png"))
        self.assertEqual(draw.call_args.args[1], ["EDM"])

    def test_incident08_unknown_date_or_owner_never_gets_template(self):
        for old, new in (("on Saturday", "recently"), ("Edmonton Oilers", "Toronto Maple Leafs"),
                         ("did not return", "returned")):
            with self.subTest(new=new):
                original = self.story.text
                self.story.text = original.replace(old, new)
                self.assertIsNone(self.packet())
                self.story.text = original

    def test_incident08_fetch_timestamp_does_not_invalidate_same_approval(self):
        d = {"text": "same", "data": {"source_snapshot": {"content_hash": "a", "fetched_at": "first"}}}
        other = copy.deepcopy(d)
        other["data"]["source_snapshot"]["fetched_at"] = "second"
        self.assertEqual(editorial_queue.fingerprint(d), editorial_queue.fingerprint(other))
        other["text"] = "changed"
        self.assertNotEqual(editorial_queue.fingerprint(d), editorial_queue.fingerprint(other))

    def test_incident08_unused_tag_metadata_does_not_create_new_version(self):
        raw = {"tags": [{"slug": "teamid-22", "extraData": {"abbreviation": "EDM", "label": "old"}}]}
        other = copy.deepcopy(raw)
        other["tags"][0]["extraData"]["label"] = "new"
        self.assertEqual(source_watch.digest("same", "same", {}, raw),
                         source_watch.digest("same", "same", {}, other))

    def test_incident08_new_parser_does_not_auto_reopen_legacy_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-11-08_story-legacy.json"
            old = {"data": {"slug": self.story.slug, "source_snapshot": fact_packet.snapshot(self.story),
                            "event_revision": {"complete": False}, "auto": False}}
            path.write_text(json.dumps(old), encoding="utf-8")
            before = path.read_bytes()
            self.story.text += "\n\nUpdated background statistic."
            match = story_provenance.equivalent_draft(self.story, self.packet(), Path(tmp), "2026-11-08")
            self.assertIsNotNone(match)
            self.assertEqual(match[0], path)
            self.assertEqual(path.read_bytes(), before)

    def test_incident08_verified_injury_reaches_auto_delivery_once(self):
        p = self.packet()
        self.assertIsNotNone(p)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch("news.editorial_lifecycle.utcnow", return_value=self.now), \
                patch("news.editorial_queue.datetime") as clock, \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456",
                                          "OWNER_CHAT_ID": "123"}):
            clock.now.return_value = self.now
            clock.fromisoformat = datetime.fromisoformat
            source = fact_packet.snapshot(self.story)
            source["fetched_at"] = self.now.isoformat()
            data = {"auto": True, "source_snapshot": source, "fact_packet": p, "packet_hash": fact_packet.key(p),
                    "event_revision": fact_packet.revision(p), "expires_at": fact_packet.expires_at(p)}
            path = publish.save_draft("2026-11-08", fact_packet.caption(p, source, "2026-11-08"), [],
                                      "fact_template_v1", kind="story-test", data=data)
            self.assertEqual(editorial_lifecycle.classify(json.loads(path.read_text()), "story-test", self.now)[0],
                             "ready")
            sender = Mock(return_value={"ok": True, "result": {"message_id": 101}})
            self.assertTrue(publish.publish("2026-11-08", ["tg"], sender, "story-test", automatic=True)[0])
            calls = sender.call_count
            self.assertTrue(publish.publish("2026-11-08", ["tg"], sender, "story-test", automatic=True)[0])
            self.assertEqual(sender.call_count, calls)


if __name__ == "__main__":
    unittest.main()
