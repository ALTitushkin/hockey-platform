"""Independent negative and offline integration checks for incident 08.11."""

import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import test_publication_stabilization as incident

from news import (
    editorial_queue,
    event_registry,
    fact_packet,
    publish,
    revalidation,
    source_watch,
    stories,
    story_validation,
)


class StabilizationQA(unittest.TestCase):
    def setUp(self):
        incident.Stabilization.setUp(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)
        out = patch.object(publish, "OUT", self.out)
        out.start()
        self.addCleanup(out.stop)
        clock = patch("news.editorial_lifecycle.utcnow", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def raw(self):
        return {"_entityId": "incident", "slug": "oilers-injury", "headline": "Nugent-Hopkins injured for Oilers",
                "contentDate": self.now.isoformat(), "selfUrl": "https://forge-dapi.d3.nhle.com/incident",
                "tags": [{"slug": "playerid-8476454"}, {"slug": "nhl-created"},
                         {"slug": "teamid-22", "extraData": {"abbreviation": "EDM"}}]}

    def draw(self, *args, **kwargs):
        path = args[-1]
        path.write_bytes(b"offline-image")
        return path

    def test_packet_caption_image_and_expiry_mutations_are_rejected(self):
        p = fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN)
        source = fact_packet.snapshot(self.story)
        image = self.out / "image.png"
        image.write_bytes(b"image")
        d = {"text": fact_packet.caption(p, source, "2026-11-08"), "card": str(image),
             "data": {"fact_packet": p, "packet_hash": fact_packet.key(p), "source_snapshot": source,
                      "event_revision": fact_packet.revision(p),
                      "expires_at": fact_packet.expires_at(p), "card_spec": fact_packet.card_spec(p),
                      "card_hash": story_validation.image_hash(image)}}
        self.assertEqual(story_validation.check(d, "2026-11-08"), [])
        variants = [copy.deepcopy(d) for _ in range(6)]
        variants[0]["text"] += " Он вернулся."
        variants[1]["data"]["card_spec"]["teams"] = ["VAN"]
        variants[2]["data"]["expires_at"] = "2099-01-01T00:00:00+03:00"
        variants[3]["data"]["fact_packet"]["claims"][0]["club"] = "VAN"
        variants[4]["data"]["event_revision"]["actors"] = [1]
        variants[5]["data"].pop("event_revision")
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertTrue(story_validation.check(variant, "2026-11-08"))
        image.write_bytes(b"replaced at same path")
        self.assertTrue(story_validation.check(d, "2026-11-08"))

    def test_refresh_late_decision_is_not_overwritten_during_render(self):
        path = publish.save_draft("2026-11-08", "legacy", [], "review", kind="story-test",
                                  data={"slug": "oilers-injury", "auto": False})
        old = editorial_queue.fingerprint(json.loads(path.read_text()))[:16]
        def racing_draw(*args, **kwargs):
            result = self.draw(*args, **kwargs)
            publish.reject("2026-11-08", "story-test", expected=old)
            return result
        with patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)), \
                patch.object(stories, "render_story_card", side_effect=racing_draw):
            with self.assertRaises(ValueError):
                revalidation.refresh("2026-11-08", "story-test", old, self.now,
                                     Mock(side_effect=[{"items": [self.raw()]}, {}]),
                                     self.names, self.teams, lambda pids, reg: self.names)
        preserved = json.loads(path.read_text())
        self.assertTrue(preserved["rejected"])
        self.assertEqual(preserved["text"], "legacy")

    def test_source_return_to_previous_body_reuses_identity(self):
        state = {}
        raw = self.raw()
        parsed = stories.parse_item(raw)
        parsed.text, parsed.en = "version A", {}
        source_watch.remember(state, raw, parsed, self.now)
        items, _ = source_watch.prepare([raw], state, self.now + timedelta(minutes=16),
                                        stories.parse_item, lambda s: ("version B", {}))
        candidate = items[0]
        changed = stories.parse_item(candidate)
        changed.text, changed.en = "version B", {}
        source_watch.remember(state, candidate, changed, self.now + timedelta(minutes=16))
        items, _ = source_watch.prepare([raw], state, self.now + timedelta(minutes=32),
                                        stories.parse_item, lambda s: ("version A", {}))
        self.assertEqual(items[0]["_entityId"], "incident")

    def test_incident_cannot_ignore_explicit_historical_year(self):
        self.story.text = self.story.text.replace("on Saturday", "on Saturday, November 1, 2025")
        self.assertIsNone(fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN))

    def test_incident_cannot_ignore_later_return_in_same_lead(self):
        self.story.text = self.story.text.replace("did not return to the game.",
                                                 "did not return to the game initially, but returned later.")
        self.assertIsNone(fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN))

    def test_review_refresh_is_version_bound_and_never_sends(self):
        path = publish.save_draft("2026-11-08", "legacy", [], "review", kind="story-test",
                                  data={"slug": "oilers-injury", "auto": False})
        old = editorial_queue.fingerprint(json.loads(path.read_text()))[:16]
        fetch = Mock(side_effect=[{"items": [self.raw()]}, {}])
        with patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.object(publish, "tg_send") as send:
            ok, _ = revalidation.refresh("2026-11-08", "story-test", old, self.now, fetch,
                                         self.names, self.teams, lambda pids, reg: self.names)
        self.assertTrue(ok)
        send.assert_not_called()
        updated = json.loads(path.read_text())
        self.assertEqual(story_validation.check(updated, "2026-11-08"), [])
        self.assertEqual(updated["published"], [])
        with self.assertRaises(ValueError):
            revalidation.refresh("2026-11-08", "story-test", old, self.now, Mock(),
                                 self.names, self.teams, Mock())

    def test_refresh_uses_current_publication_day_without_redating_the_event(self):
        path = publish.save_draft("2026-11-07", "legacy", [], "review", kind="story-test",
                                  data={"slug": "oilers-injury", "auto": False})
        old = editorial_queue.fingerprint(json.loads(path.read_text(encoding="utf-8")))[:16]
        fetch = Mock(side_effect=[{"items": [self.raw()]}, {}])
        with patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw):
            ok, _ = revalidation.refresh("2026-11-07", "story-test", old, self.now, fetch,
                                         self.names, self.teams, lambda pids, reg: self.names)
        self.assertTrue(ok)
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(updated["date"], "2026-11-07")
        self.assertEqual(updated["data"]["publication_date"], "2026-11-08")
        self.assertEqual(updated["data"]["fact_packet"]["claims"][0]["date"], "2026-11-07")
        self.assertEqual(story_validation.check(updated, "2026-11-07"), [])
        self.assertIn("#Травмы · 8 ноября", updated["text"])

    def test_refresh_never_reads_source_when_old_document_delivery_is_unresolved(self):
        p = fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN)
        path = publish.save_draft("2026-11-08", "legacy", [], "review", kind="story-test",
                                  data={"slug": "oilers-injury", "auto": False})
        before = path.read_bytes()
        old = editorial_queue.fingerprint(json.loads(before))[:16]
        ledger = event_registry.Registry(self.out / "event_registry.sqlite3")
        try:
            ledger.reserve(fact_packet.revision(p), "tg:-100123456", path.name)
            for status in ("sending", "uncertain"):
                with self.subTest(status=status):
                    with ledger.db:
                        ledger.db.execute("UPDATE publications SET status=? WHERE document=?", (status, path.name))
                    fetch = Mock(side_effect=AssertionError("unresolved delivery must block before network"))
                    with self.assertRaises(ValueError):
                        revalidation.refresh("2026-11-08", "story-test", old, self.now, fetch,
                                             self.names, self.teams, Mock())
                    fetch.assert_not_called()
                    self.assertEqual(path.read_bytes(), before)
        finally:
            ledger.close()

    def test_changed_background_with_same_claims_does_not_render_or_notify_again(self):
        raw = self.raw()
        write = Mock(side_effect=AssertionError("known fact must not call model"))
        send = Mock(return_value={"ok": True, "result": {"message_id": 101}})
        fetch = Mock(side_effect=lambda url: {"items": [raw]} if url == stories.FEED else {})
        body = Mock(return_value=(self.story.text, self.story.en))
        def deliver(day, kind):
            return publish.review(day, send, kind=kind)
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "body_text", body), \
                patch.object(stories, "render_story_card", side_effect=self.draw) as draw, \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "OWNER_CHAT_ID": "123"}):
            for tick in range(2):
                if tick:
                    raw = {**raw, "_entityId": "updated", "_editorial_origin": "incident"}
                    body.return_value = (self.story.text + "\n\nHe has 11 points this season.", self.story.en)
                stories.process(self.now + timedelta(minutes=16 * tick), fetch, self.names, self.teams,
                                lambda pids, reg: self.names, write, lambda: [], deliver, Mock())
        self.assertEqual(draw.call_count, 1)
        self.assertEqual(send.call_count, 2)  # First photo and controls only.
        self.assertEqual(len(list(self.out.glob("*_story-*.json"))), 1)
        write.assert_not_called()

    def test_new_parser_does_not_auto_promote_historical_incomplete_review(self):
        frozen = fact_packet.snapshot(self.story)
        frozen["fetched_at"] = self.now.isoformat()
        path = publish.save_draft("2026-11-08", "legacy prose", [], "review", kind="story-original",
                                  data={"slug": self.story.slug, "auto": False, "source_snapshot": frozen,
                                        "event_revision": {"complete": False, "family": "health"}})
        before = path.read_bytes()
        raw = {**self.raw(), "_entityId": "updated"}
        deliver = Mock(return_value=(True, "review already notified"))
        write = Mock(side_effect=AssertionError("old review must not be regenerated"))
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "body_text", return_value=(
                    self.story.text + "\n\nNew background: he has 11 points.", self.story.en)), \
                patch.object(stories, "render_story_card") as draw:
            stories.process(self.now,
                            lambda url: {"items": [raw]} if url == stories.FEED else {},
                            self.names, self.teams, lambda pids, reg: self.names, write,
                            lambda: [], deliver, Mock())
        deliver.assert_called_once_with("2026-11-08", "story-original")
        draw.assert_not_called()
        write.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(self.out.glob("*_story-*.json"))), 1)

    def test_process_builds_supported_fact_without_llm_and_delivers_once(self):
        write = Mock(side_effect=AssertionError("supported fact must not require LLM"))
        send = Mock(return_value={"ok": True, "result": {"message_id": 101}})
        raw = self.raw()
        def fetch(url):
            return {"items": [raw]} if url == stories.FEED else {}
        def deliver(day, kind):
            ok, lines = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(lines)
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}):
            for _ in range(2):
                stories.process(self.now, fetch, self.names, self.teams, lambda pids, reg: self.names,
                                write, lambda: [], deliver, Mock())
        self.assertEqual(send.call_count, 1)
        write.assert_not_called()
        drafts = list(self.out.glob("*_story-*.json"))
        self.assertEqual(len(drafts), 1)
        self.assertEqual(json.loads(drafts[0].read_text())["published"], ["tg"])

    def test_report_sections_keep_completed_action_and_owner(self):
        self.story.headline = "NHL Status Report: Nikishin makes season debut"
        self.story.pids, self.story.teams = set(), set()
        self.story.en = {1: "Alexander Nikishin", 2: "Other Player"}
        self.story.text = ("## Carolina Hurricanes\n\nAlexander Nikishin made his season debut for the Hurricanes "
                           "against the Chicago Blackhawks on Saturday.\n\n"
                           "## Edmonton Oilers\n\nOther Player is injured on Saturday.")
        p = fact_packet.extract(self.story, {"1": {"ru": "Александр Никишин"}},
                                {"CAR": "Каролина", "EDM": "Эдмонтон"}, stories.TEAM_EN)
        self.assertIsNotNone(p)
        self.assertEqual(p["claims"][0]["club"], "CAR")
        self.assertEqual(p["claims"][0]["kind"], "season_debut")
        self.assertEqual(fact_packet.verify(p, fact_packet.snapshot(self.story), fact_packet.render(p)), [])

    def test_report_clock_parentheses_preserve_expected_and_do_not_roll_stale_weekday(self):
        self.story.headline = "NHL Status Report: Nikishin to make season debut"
        self.story.pids, self.story.teams = set(), set()
        self.story.en = {1: "Alexander Nikishin"}
        self.story.date = self.now - timedelta(days=1)  # Saturday forecast about Saturday.
        self.story.text = ("## Carolina Hurricanes\n\nAlexander Nikishin is expected to make his season debut "
                           "for the Hurricanes against the Chicago Blackhawks on Saturday (8 p.m. ET; HHN).")
        names, teams = {"1": {"ru": "Александр Никишин"}}, {"CAR": "Каролина"}
        p = fact_packet.extract(self.story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(p)
        self.assertEqual(p["claims"][0]["kind"], "expected_debut")
        self.assertEqual(p["claims"][0]["modality"], "expected")
        self.assertEqual(p["claims"][0]["date"], "2026-11-07")
        self.assertIn("может", fact_packet.render(p))
        self.assertEqual(fact_packet.verify(p, fact_packet.snapshot(self.story), fact_packet.render(p)), [])
        self.story.date = self.now  # Sunday update still mentioning Saturday cannot mean next Saturday.
        self.assertIsNone(fact_packet.extract(self.story, names, teams, stories.TEAM_EN))
