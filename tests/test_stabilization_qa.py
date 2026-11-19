"""Independent negative and offline integration checks for incident 08.11."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import test_publication_stabilization as incident
from PIL import Image

from news import (
    editorial_lifecycle,
    editorial_queue,
    event_registry,
    fact_packet,
    match_facts,
    publish,
    revalidation,
    source_watch,
    stories,
    story_provenance,
    story_validation,
)
from news.digest import NOT_PLAYED, render_tonight
from news.nhl import GameReport, GoalieLine, SkaterLine


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
        queue_clock = patch("news.editorial_queue.datetime")
        mocked_datetime = queue_clock.start()
        mocked_datetime.now.return_value = self.now
        mocked_datetime.fromisoformat = datetime.fromisoformat
        self.addCleanup(queue_clock.stop)

    def raw(self):
        return {"_entityId": "incident", "slug": "oilers-injury", "headline": "Nugent-Hopkins injured for Oilers",
                "contentDate": self.now.isoformat(), "selfUrl": "https://forge-dapi.d3.nhle.com/incident",
                "tags": [{"slug": "playerid-8476454"}, {"slug": "nhl-created"},
                         {"slug": "teamid-22", "extraData": {"abbreviation": "EDM"}}]}

    def test_night_lead_stays_inside_selected_highlight_game(self):
        reports = [
            GameReport(1, "TBL", "NYR", 4, 3, "OT",
                       skaters=[SkaterLine(10, "TBL", 1, 1, 2, 4)],
                       goalies=[GoalieLine(11, "TBL", 20, 23, "W")]),
            GameReport(2, "PIT", "LAK", 5, 2, "REG",
                       skaters=[SkaterLine(20, "PIT", 1, 1, 2, 3)],
                       goalies=[GoalieLine(21, "PIT", 26, 28, "W")]),
        ]
        players = {"11": {"surname": "Василевский"}, "21": {"surname": "Мурашов"}}
        lead = match_facts.night_lead(reports, players, {"TBL": "Тампа-Бэй", "NYR": "Рейнджерс"},
                                      [(10, [])])
        self.assertIn("Василевский", lead)
        self.assertNotIn("Мурашов", lead)

    def test_previous_nonparticipation_is_not_presented_as_questionable(self):
        games = [{"start": "2026-11-15T00:00:00Z", "home": "EDM", "away": "VAN"}]
        text, _ = render_tonight(games, {}, {"EDM": "Эдмонтон", "VAN": "Ванкувер"},
                                 "2026-11-14", timezone.utc,
                                 {"EDM": [(847, "Баль", NOT_PLAYED)]})
        self.assertIn("Не играли прошлый матч", text)
        self.assertNotIn("Под вопросом", text)

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

    def test_untyped_legacy_draft_is_not_reused_as_publishable_equivalent(self):
        source = fact_packet.snapshot(self.story)
        path = publish.save_draft("2026-11-08", "malformed old prose", [], "free paraphrase",
                                  kind="story-legacy", data={"slug": self.story.slug, "auto": False,
                                                               "source_snapshot": source})
        self.assertIsNone(story_provenance.equivalent_draft(self.story, None, self.out, "2026-11-08"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["text"], "malformed old prose")

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
        draft = next(self.out.glob("*_story-*.json"))
        self.assertEqual(send.call_count, 1, msg=draft.read_text(encoding="utf-8"))
        write.assert_not_called()
        drafts = list(self.out.glob("*_story-*.json"))
        self.assertEqual(len(drafts), 1)
        self.assertEqual(json.loads(drafts[0].read_text())["published"], ["tg"])

    def test_status_report_selected_debut_reaches_auto_delivery_once(self):
        now = self.now + timedelta(days=4)
        story = stories.Story(
            "status-report", "nhl-status-report-news-and-notes-november-12-2026",
            "NHL Status Report: Terry makes season debut for Ducks", "", now,
            "injury_minor", set(), set(), True,
            text=("## Anaheim Ducks\n\nTroy Terry made his season debut against the Nashville Predators "
                  "on Wednesday. The forward had surgery in June and missed 61 games last season.\n\n"
                  "## Tampa Bay Lightning\n\nBrayden Point was placed on injured reserve."),
            en={8478873: "Troy Terry", 8478010: "Brayden Point"})
        raw = {"id": "status-report"}
        send = Mock(return_value={"ok": True, "result": {"message_id": 909}})
        write = Mock(side_effect=AssertionError("typed report fact must not call LLM"))
        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "select", return_value=[story]), \
                patch.object(stories, "body_text", return_value=(story.text, story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}):
            stories.process(now, lambda url: {"items": [raw]} if url == stories.FEED else {},
                            {}, {"ANA": "Анахайм"},
                            lambda pids, registry: {"8478873": {"ru": "Трой Терри", "surname": "Терри"}},
                            write, lambda: [], deliver, Mock())
        write.assert_not_called()
        send.assert_called_once()
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        self.assertTrue(draft["data"]["auto"])
        self.assertEqual(draft["data"]["fact_packet"]["claims"][0]["kind"], "season_debut")
        self.assertEqual(draft["data"]["fact_packet"]["claims"][0]["subject"], 8478873)

    def test_live_staal_return_source_reaches_auto_delivery_once(self):
        now = datetime(2026, 11, 14, 16, 9, tzinfo=timezone.utc)
        story = stories.Story(
            "live-staal", "jordan-staal-returns-to-hurricanes-lineup-for-global-series-finale",
            "Staal to return for Hurricanes in Global Series finale against Kraken", "", now,
            "return", {8473533}, {"CAR"}, True,
            text=("Jordan Staal will return for the Carolina Hurricanes against the Seattle Kraken in the "
                  "2026 NHL Global Series Finland finale on Saturday.\n\n"
                  "The 38-year-old center hasn't played since Oct. 10, missing the past 14 games "
                  "with a calf injury.\n\n"
                  "He won the Conn Smythe Trophy last season as most valuable player of the playoffs.\n\n"
                  "\"We're getting him back,\" Carolina coach Rod Brind'Amour said. "
                  "\"I don't expect a ton out of him tonight.\""),
            en={8473533: "Jordan Staal", 8482093: "Seth Jarvis", 8476422: "Mike Reilly"})
        actors = {"8473533": {"ru": "Джордан Стаал", "surname": "Стаал"}}
        self.assertIsNotNone(fact_packet.extract(story, actors, {"CAR": "Каролина"}, stories.TEAM_EN))
        retracted = copy.deepcopy(story)
        retracted.text += "\n\nJordan Staal is no longer expected to return on Saturday."
        self.assertIsNone(fact_packet.extract(retracted, actors, {"CAR": "Каролина"}, stories.TEAM_EN))
        send = Mock(return_value={"ok": True, "result": {"message_id": 912}})
        write = Mock(side_effect=AssertionError("confirmed return has a typed template"))

        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)

        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "select", return_value=[story]), \
                patch.object(stories, "body_text", return_value=(story.text, story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}):
            stories.process(now, lambda url: {"items": [{"id": story.eid}]} if url == stories.FEED else {},
                            actors, {"CAR": "Каролина"}, lambda pids, registry: actors,
                            write, lambda: [], deliver, Mock())

        write.assert_not_called()
        send.assert_called_once()
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        claim = draft["data"]["fact_packet"]["claims"][0]
        self.assertTrue(draft["data"]["auto"])
        self.assertEqual(claim["kind"], "expected_return")
        self.assertEqual(claim["subject"], 8473533)
        self.assertEqual(claim["date"], "2026-11-14")
        spec = draft["data"]["card_spec"]
        self.assertEqual(spec["hero_id"], 8473533)
        self.assertEqual(spec["teams"], ["CAR"])
        self.assertIn("Стаал может вернуться", spec["headline"])
        self.assertIn(spec["headline"], draft["text"])

    def test_two_player_injury_reaches_auto_delivery_once(self):
        now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        story = stories.Story(
            "avalanche-injuries", "nathan-mackinnon-cale-makar-exit-game-for-colorado-avalanche",
            "MacKinnon, Makar sustain lower-body injuries in Avalanche loss", "", now,
            "injury_minor", {8477492, 8480069}, {"COL"}, True,
            text=("Nathan MacKinnon and Cale Makar each sustained a lower-body injury in the second period "
                  "of a 4-3 overtime loss for the Colorado Avalanche against the Ottawa Senators on Thursday.\n\n"
                  "Makar briefly returned later, then stayed on the bench for the rest of the period."),
            en={8477492: "Nathan MacKinnon", 8480069: "Cale Makar"})
        actor_records = {"8477492": {"ru": "Натан Маккиннон", "surname": "Маккиннон"},
                         "8480069": {"ru": "Кейл Макар", "surname": "Макар"}}
        send = Mock(return_value={"ok": True, "result": {"message_id": 910}})
        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "select", return_value=[story]), \
                patch.object(stories, "body_text", return_value=(story.text, story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}):
            stories.process(now, lambda url: {"items": [{"id": story.eid}]} if url == stories.FEED else {},
                            actor_records, {"COL": "Колорадо"}, lambda pids, registry: actor_records,
                            Mock(side_effect=AssertionError("typed group fact must not use LLM")),
                            lambda: [], deliver, Mock())
        send.assert_called_once()
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(draft["data"]["event_revision"]["actors"], [8477492, 8480069])
        self.assertEqual(draft["published"], ["tg"])
        self.assertTrue(draft["data"]["auto"])

    def test_injury_duration_update_uses_source_freshness_and_publishes_once(self):
        now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        story = stories.Story(
            "avalanche-injury-durations", "mackinnon-makar-injuries",
            "MacKinnon out one month, Makar two weeks", "", now, "injury",
            {8477492, 8480069}, {"COL"}, True,
            text=("Nathan MacKinnon will be out one month and Cale Makar will be sidelined two weeks "
                  "for the Colorado Avalanche.\n\n"
                  "Each sustained a lower-body injury in the second period of a 4-3 overtime loss "
                  "for the Colorado Avalanche against the Ottawa Senators on Thursday."),
            en={8477492: "Nathan MacKinnon", 8480069: "Cale Makar"})
        actors = {"8477492": {"ru": "Натан Маккиннон", "surname": "Маккиннон"},
                  "8480069": {"ru": "Кейл Макар", "surname": "Макар"}}
        send = Mock(return_value={"ok": True, "result": {"message_id": 911}})

        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)

        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "select", return_value=[story]), \
                patch.object(stories, "body_text", return_value=(story.text, story.en)), \
                patch.object(stories, "render_story_card", side_effect=self.draw), \
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}):
            stories.process(now, lambda url: {"items": [{"id": story.eid}]} if url == stories.FEED else {},
                            actors, {"COL": "Колорадо"}, lambda pids, registry: actors,
                            Mock(side_effect=AssertionError("typed duration must not use LLM")),
                            lambda: [], deliver, Mock())

        send.assert_called_once()
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        packet = draft["data"]["fact_packet"]
        self.assertTrue(draft["data"]["auto"])
        self.assertEqual(draft["published"], ["tg"])
        self.assertEqual([claim["date"] for claim in packet["claims"]], ["2026-11-05", "2026-11-05"])
        self.assertEqual([claim["published_date"] for claim in packet["claims"]], ["2026-11-08", "2026-11-08"])
        self.assertEqual(draft["data"]["expires_at"], "2026-11-10T00:00:00+03:00")
        self.assertEqual(draft["data"]["card_spec"]["label"], "ТРАВМА")
        self.assertIn("Натан Маккиннон выбыл на 1 месяц", draft["text"])
        self.assertIn("Кейл Макар — на 2 недели", draft["text"])
        self.assertEqual(story_validation.check(draft, "2026-11-08"), [])
        ok, report = publish.publish("2026-11-08", ["tg"], send, next(p.name.split("_", 1)[1][:-5]
                                                                       for p in self.out.glob("*_story-*.json")),
                                    automatic=True)
        self.assertTrue(ok, report)
        send.assert_called_once()
        corrupted = copy.deepcopy(draft)
        corrupt_packet = corrupted["data"]["fact_packet"]
        corrupt_packet["claims"][1]["duration"] = 1
        corrupted["published"] = []
        corrupted["data"]["packet_hash"] = fact_packet.key(corrupt_packet)
        corrupted["data"]["event_revision"] = fact_packet.revision(corrupt_packet)
        corrupted["data"]["card_spec"] = fact_packet.card_spec(corrupt_packet)
        corrupted["text"] = fact_packet.caption(corrupt_packet, corrupted["data"]["source_snapshot"],
                                                "2026-11-08")
        (self.out / "2026-11-08_story-corrupt.json").write_text(
            json.dumps(corrupted, ensure_ascii=False), encoding="utf-8")
        rejected, reasons = publish.publish("2026-11-08", ["tg"], send, "story-corrupt", automatic=True)
        self.assertFalse(rejected)
        self.assertIn("утверждения не соответствуют повторному разбору доказательств", " ".join(reasons))
        send.assert_called_once()
        stale_story = copy.deepcopy(story)
        stale_story.date = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        stale_packet = fact_packet.extract(stale_story, actors, {"COL": "Колорадо"}, stories.TEAM_EN)
        stale_draft = {"date": "2026-11-08", "data": {
            "source_snapshot": fact_packet.snapshot(stale_story),
            "event_revision": fact_packet.revision(stale_packet),
            "expires_at": fact_packet.expires_at(stale_packet)}}
        status, reasons = editorial_lifecycle.classify(stale_draft, "story-old", now)
        self.assertEqual((status, reasons[0]), ("expired", "окно публикации этого сценария закрыто"))

    def test_legacy_two_player_review_refreshes_to_verified_card_without_sending(self):
        now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        story = stories.Story(
            "avalanche-injuries", "nathan-mackinnon-cale-makar-exit-game-for-colorado-avalanche",
            "MacKinnon, Makar sustain lower-body injuries in Avalanche loss", "", now,
            "injury_minor", {8477492, 8480069}, {"COL"}, True,
            text=("Nathan MacKinnon and Cale Makar each sustained a lower-body injury in the second period "
                  "of a 4-3 overtime loss for the Colorado Avalanche against the Ottawa Senators on Thursday.\n\n"
                  "Makar briefly returned later, then stayed on the bench for the rest of the period."),
            en={8477492: "Nathan MacKinnon", 8480069: "Cale Makar"})
        actor_records = {"8477492": {"ru": "Натан Маккиннон"}, "8480069": {"ru": "Кейл Макар"}}
        path = publish.save_draft("2026-11-13", "old mixed prose", [], "legacy", "old.png",
                                  kind="story-multi", data={"slug": story.slug, "auto": False})
        expected = editorial_queue.fingerprint(json.loads(path.read_text(encoding="utf-8")))[:16]
        fetch = Mock(side_effect=[{"items": [{"slug": story.slug}]}, {}])
        with patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=(story.text, story.en)), \
                patch.object(publish, "tg_send") as send:
            ok, info = revalidation.refresh("2026-11-13", "story-multi", expected, now, fetch,
                                             actor_records, {"COL": "Колорадо"}, lambda pids, registry: actor_records)
        self.assertTrue(ok, info)
        send.assert_not_called()
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(updated["data"]["auto"])
        self.assertEqual(updated["data"]["event_revision"]["actors"], [8477492, 8480069])
        self.assertEqual(story_validation.check(updated, "2026-11-13"), [])
        with Image.open(updated["card"]) as image:
            self.assertEqual(image.size[0], 1080)

    def test_unsupported_story_becomes_source_task_without_generated_text_or_card(self):
        write = Mock(side_effect=AssertionError("unsupported event must not be paraphrased"))
        render = Mock(side_effect=AssertionError("unsupported event must not get a ready card"))
        delivered = []
        raw = self.raw()
        publish.save_draft("2026-11-08", "Бал подписал операцию", [], "legacy free paraphrase",
                           "old-empty-card.png", kind="story-incident", data={"slug": "oilers-injury",
                                                                                 "auto": False})
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)), \
                patch.object(fact_packet, "extract", return_value=None), \
                patch.object(stories, "render_story_card", render):
            stories.process(self.now, lambda url: {"items": [raw]} if url == stories.FEED else {},
                            self.names, self.teams, lambda pids, reg: self.names, write, lambda: [],
                            lambda day, kind: delivered.append((day, kind)) or (True, "queued"), Mock())
        write.assert_not_called()
        render.assert_not_called()
        self.assertEqual(len(delivered), 1)
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        self.assertIsNone(draft["card"])
        self.assertFalse(draft["data"]["auto"])
        self.assertTrue(draft["data"]["editorial_task"])
        self.assertTrue(draft["issues"])
        self.assertIn("Открыть источник", draft["text"])
        self.assertNotIn("Бал подписал операцию", draft["text"])

    def test_legacy_quarantine_preserves_document_with_uncertain_delivery_ledger(self):
        path = publish.save_draft("2026-11-08", "old payload", [], "legacy", "old.png",
                                  kind="story-incident", data={"slug": "oilers-injury", "auto": False})
        before = path.read_bytes()
        packet = fact_packet.extract(self.story, self.names, self.teams, stories.TEAM_EN)
        ledger = event_registry.Registry(self.out / "event_registry.sqlite3")
        try:
            ledger.reserve(fact_packet.revision(packet), "tg:-100123456", path.name)
        finally:
            ledger.close()
        deliver = Mock(return_value=(False, "delivery reconciliation required"))
        with patch.object(stories, "STATE", self.out / "stories_state.json"), \
                patch.object(stories, "body_text", side_effect=AssertionError("must not replace unresolved")), \
                patch.object(stories, "render_story_card") as draw:
            stories.process(self.now, lambda url: {"items": [self.raw()]} if url == stories.FEED else {},
                            self.names, self.teams, lambda pids, reg: self.names,
                            Mock(side_effect=AssertionError("must not paraphrase")), lambda: [], deliver, Mock())
        self.assertEqual(path.read_bytes(), before)
        draw.assert_not_called()
        deliver.assert_called_once()

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

    def test_status_report_extracts_only_headline_players_current_event(self):
        cases = [
            ("Troy Terry makes season debut", "Troy Terry", "Anaheim Ducks",
             "Troy Terry made his season debut against the Nashville Predators on Wednesday. "
             "He had surgery in June and missed 61 games last season.", "ANA", "season_debut", "2026-11-11"),
            ("Heiskanen to return", "Miro Heiskanen", "Dallas Stars",
             "Miro Heiskanen will return for the Stars to play the Vegas Golden Knights on Thursday "
             "(10 p.m. ET), the first of consecutive road games.",
             "DAL", "expected_return", "2026-11-12"),
            ("Kevin Fiala to make season debut", "Kevin Fiala", "Los Angeles Kings",
             "Kevin Fiala is expected to make his season debut against the New York Islanders "
             "on Thursday (10 p.m. ET; ESPN+). Fiala sustained fractures in February.",
             "LAK", "expected_debut", "2026-11-12"),
            ("Linus Ullmark to return", "Linus Ullmark", "Ottawa Senators",
             "Linus Ullmark will return to the lineup for the Senators against the Colorado Avalanche "
             "on Thursday (7 p.m. ET; RDS2), coach Travis Green said. He missed nine games.",
             "OTT", "expected_return", "2026-11-12"),
            ("Brock Faber could make season debut", "Brock Faber", "Minnesota Wild",
             "Brock Faber could make his season debut against the Anaheim Ducks on Saturday. "
             "His minutes were managed in practice.", "MIN", "expected_debut", "2026-11-14"),
        ]
        for headline, player, section, body, club, kind, action_date in cases:
            with self.subTest(player=player):
                pid = 100
                self.story.headline = f"NHL Status Report: {headline}"
                self.story.date = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
                self.story.pids, self.story.teams = set(), set()
                self.story.en = {pid: player, 200: "Other Player"}
                self.story.text = f"## {section}\n\n{body}\n\n## Other Club\nOther Player is injured."
                names = {str(pid): {"ru": f"Игрок {pid}"}}
                teams = {club: "Клуб"}
                packet = fact_packet.extract(self.story, names, teams, stories.TEAM_EN)
                self.assertIsNotNone(packet)
                self.assertEqual(packet["claims"][0]["kind"], kind)
                self.assertEqual(packet["claims"][0]["date"], action_date)
                self.assertNotIn("missed", packet["claims"][0]["evidence"].lower())
                self.assertEqual(fact_packet.card_spec(packet)["label"],
                                 "ДЕБЮТ" if "debut" in kind else "ВОЗВРАЩЕНИЕ")
                self.assertIn("#Дебюты" if "debut" in kind else "#Возвращения",
                              fact_packet.caption(packet, fact_packet.snapshot(self.story), "2026-11-12"))
                self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(self.story),
                                                    fact_packet.render(packet)), [])

    def test_single_story_expected_debut_and_could_return_are_typed(self):
        cases = [
            ("Fiala to make season debut for Kings", "Kevin Fiala", 8477942, "LAK", "injury_minor",
             datetime(2026, 11, 11, 12, tzinfo=timezone.utc),
             "Kevin Fiala will make his season debut for the Los Angeles Kings against the New York Islanders "
             "on Thursday (10 p.m. ET; ESPN+).\n\nHe sustained fractures at the Olympics in February.",
             "expected_debut", "2026-11-12"),
            ("Staal could return for Hurricanes", "Jordan Staal", 8473533, "CAR", "return",
             datetime(2026, 11, 13, 12, tzinfo=timezone.utc),
             "Jordan Staal could return for the Carolina Hurricanes against the Seattle Kraken "
             "at the 2026 NHL Global Series in Helsinki on Saturday (1 p.m. ET; HHN).",
             "expected_return", "2026-11-14"),
        ]
        for headline, english, pid, club, kind, date, text, claim_kind, action_date in cases:
            with self.subTest(player=english):
                story = stories.Story("single", "single", headline, "", date, kind, {pid}, {club}, True,
                                      text=text, en={pid: english})
                names = {str(pid): {"ru": f"Тест {english}", "surname": english.split()[-1]}}
                packet = fact_packet.extract(story, names, {club: "Клуб"}, stories.TEAM_EN)
                self.assertIsNotNone(packet)
                self.assertEqual(packet["claims"][0]["kind"], claim_kind)
                self.assertEqual(packet["claims"][0]["date"], action_date)
                self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story),
                                                    fact_packet.render(packet)), [])

    def test_club_announcement_activation_from_ir_is_dated_and_typed(self):
        story = stories.Story(
            "fiala-activation", "la-kings-activate-forward-kevin-fiala-from-injured-reserve",
            "LA Kings Activate Forward Kevin Fiala From Injured Reserve", "", self.now,
            "return", {8477942}, {"LAK"}, False,
            text=("The LA Kings have activated forward **Kevin Fiala** from injured reserve (IR).\n\n"
                  "The Kings return to action tonight against the New York Islanders."),
            en={8477942: "Kevin Fiala"})
        names = {"8477942": {"ru": "Кевин Фиала", "surname": "Фиала"}}
        teams = {"LAK": "Лос-Анджелес"}
        packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(packet)
        self.assertEqual(packet["claims"][0]["kind"], "activation")
        self.assertEqual(fact_packet.revision(packet)["phase"], "activated")
        self.assertEqual(fact_packet.revision(packet)["date_basis"], "publication_date")
        self.assertIn("из списка травмированных", fact_packet.render(packet))
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story),
                                            fact_packet.render(packet)), [])

    def test_two_player_injury_claims_keep_both_actors_and_one_game_date(self):
        story = stories.Story(
            "avalanche-injuries", "nathan-mackinnon-cale-makar-exit-game-for-colorado-avalanche",
            "MacKinnon, Makar sustain lower-body injuries in Avalanche loss", "",
            datetime(2026, 11, 13, 12, tzinfo=timezone.utc), "injury_minor",
            {8477492, 8480069}, {"COL"}, True,
            text=("Nathan MacKinnon and Cale Makar each sustained a lower-body injury in the second period "
                  "of a 4-3 overtime loss for the Colorado Avalanche against the Ottawa Senators on Thursday.\n\n"
                  "Makar briefly returned later, then stayed on the bench for the rest of the period."),
            en={8477492: "Nathan MacKinnon", 8480069: "Cale Makar"})
        names = {"8477492": {"ru": "Натан Маккиннон"}, "8480069": {"ru": "Кейл Макар"}}
        teams = {"COL": "Колорадо"}
        packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(packet)
        self.assertEqual([claim["subject"] for claim in packet["claims"]], [8477492, 8480069])
        self.assertEqual({claim["date"] for claim in packet["claims"]}, {"2026-11-12"})
        self.assertEqual(fact_packet.revision(packet)["actors"], [8477492, 8480069])
        self.assertEqual(fact_packet.revision(packet)["phase"], "injury")
        self.assertIn("Натан Маккиннон и Кейл Макар получили повреждения", fact_packet.render(packet))
        self.assertNotIn("вернулся", fact_packet.render(packet))
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story),
                                            fact_packet.render(packet)), [])

    def test_two_player_injury_durations_remain_attached_to_the_correct_actor(self):
        story = stories.Story(
            "avalanche-injury-durations", "mackinnon-makar-injuries",
            "MacKinnon out one month, Makar two weeks", "",
            datetime(2026, 11, 14, 17, 41, tzinfo=timezone.utc), "injury",
            {8477492, 8480069}, {"COL"}, True,
            text=("Nathan MacKinnon will be out one month and Cale Makar will be sidelined two weeks "
                  "for the Colorado Avalanche.\n\n"
                  "Each sustained a lower-body injury in the second period of a 4-3 overtime loss "
                  "for the Colorado Avalanche against the Ottawa Senators on Thursday."),
            en={8477492: "Nathan MacKinnon", 8480069: "Cale Makar"})
        names = {"8477492": {"ru": "Натан Маккиннон"}, "8480069": {"ru": "Кейл Макар"}}
        teams = {"COL": "Колорадо"}
        packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(packet)
        self.assertEqual([(c["subject"], c["duration"], c["duration_unit"]) for c in packet["claims"]],
                         [(8477492, 1, "month"), (8480069, 2, "week")])
        body = fact_packet.render(packet)
        self.assertIn("Натан Маккиннон выбыл на 1 месяц", body)
        self.assertIn("Кейл Макар — на 2 недели", body)
        self.assertEqual(fact_packet.revision(packet)["facts"]["duration_by_actor"], [
            {"subject": 8477492, "duration": 1, "unit": "month"},
            {"subject": 8480069, "duration": 2, "unit": "week"}])
        self.assertEqual(fact_packet.card_spec(packet)["label"], "ТРАВМА")
        self.assertEqual(fact_packet.expires_at(packet), "2026-11-16T00:00:00+03:00")
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story), body), [])
        late_utc = copy.deepcopy(story)
        late_utc.date = datetime(2026, 11, 14, 22, 30, tzinfo=timezone.utc)
        late_packet = fact_packet.extract(late_utc, names, teams, stories.TEAM_EN)
        self.assertEqual(late_packet["claims"][0]["published_date"], "2026-11-15")
        self.assertEqual(fact_packet.expires_at(late_packet), "2026-11-17T00:00:00+03:00")
        changed = copy.deepcopy(packet)
        changed["claims"][1]["duration"] = 1  # internally consistent render, wrong source fact
        changed_body = fact_packet.render(changed)
        self.assertTrue(fact_packet.verify(changed, fact_packet.snapshot(story), changed_body))

    def test_single_player_injury_duration_range_publishes_from_one_verified_packet(self):
        now = datetime(2026, 11, 14, 16, 50, tzinfo=timezone.utc)
        story = stories.Story(
            "kreider-injury-duration", "canadiens-chris-kreider-out-6-8-weeks-with-lower-body-injury",
            "Kreider out 6-8 weeks for Canadiens with lower-body injury", "", now, "injury",
            {8475184}, {"MTL"}, True,
            text=("Chris Kreider is out 6-8 weeks for the Montreal Canadiens because of a lower-body injury, "
                  "the team announced on Saturday.\n\n"
                  "The forward appeared to sustain a leg injury in a 5-2 win against the Boston Bruins "
                  "on Thursday. Kreider left at 6:27 of the third period and did not return."),
            en={8475184: "Chris Kreider"})
        names = {"8475184": {"ru": "Крис Крайдер", "surname": "Крайдер"}}
        teams = {"MTL": "Монреаль"}
        packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
        self.assertIsNotNone(packet)
        claim = packet["claims"][0]
        self.assertEqual((claim["subject"], claim["duration_min"], claim["duration_max"],
                          claim["duration_unit"], claim["region"]),
                         (8475184, 6, 8, "week", "lower"))
        self.assertEqual((claim["date"], claim["published_date"]), ("2026-11-12", "2026-11-14"))
        body = fact_packet.render(packet)
        self.assertIn("Крис Крайдер выбыл на 6–8 недель", body)
        self.assertEqual(fact_packet.revision(packet)["facts"]["duration_by_actor"], [
            {"subject": 8475184, "duration_min": 6, "duration_max": 8, "unit": "week"}])
        self.assertEqual(fact_packet.expires_at(packet), "2026-11-16T00:00:00+03:00")
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story), body), [])
        changed = copy.deepcopy(packet)
        changed["claims"][0]["duration_min"] = 5
        self.assertTrue(fact_packet.verify(changed, fact_packet.snapshot(story), fact_packet.render(changed)))
        changed_source = copy.deepcopy(story)
        changed_source.date = datetime(2026, 11, 17, 16, 50, tzinfo=timezone.utc)
        stale = fact_packet.extract(changed_source, names, teams, stories.TEAM_EN)
        self.assertEqual(fact_packet.expires_at(stale), "2026-11-19T00:00:00+03:00")

        send = Mock(return_value={"ok": True, "result": {"message_id": 928}})

        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)

        with (
                patch.object(stories, "STATE", self.out / "stories_state.json"),
                patch.object(stories, "parse_item", return_value=story),
                patch.object(stories, "select", return_value=[story]),
                patch.object(stories, "body_text", return_value=(story.text, story.en)),
                patch.object(stories, "render_story_card", side_effect=self.draw),
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}),
        ):
            stories.process(now, lambda url: {"items": [{"id": story.eid}]} if url == stories.FEED else {},
                            names, teams, lambda pids, registry: names,
                            Mock(side_effect=AssertionError("typed injury duration must not use LLM")),
                            lambda: [], deliver, Mock())
        send.assert_called_once()
        draft = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(draft["data"]["fact_packet"], packet)
        self.assertEqual(draft["data"]["card_spec"]["hero_id"], 8475184)
        self.assertEqual(draft["data"]["card_spec"]["label"], "ТРАВМА")
        self.assertIn("Крис Крайдер выбыл на 6–8 недель", draft["text"])
        self.assertEqual(draft["published"], ["tg"])
        self.assertEqual(story_validation.check(draft, "2026-11-14"), [])
        publish.publish("2026-11-14", ["tg"], send, next(p.name.split("_", 1)[1][:-5]
                       for p in self.out.glob("*_story-*.json")), automatic=True)
        send.assert_called_once()

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

    def test_status_report_will_make_debut_uses_eastern_event_day_and_expiry(self):
        self.story.headline = "NHL Status Report: Faber to make season debut for Wild against Bruins"
        self.story.slug = "nhl-status-report-news-and-notes-november-13-2026"
        self.story.date = datetime(2026, 11, 14, 20, 21, tzinfo=timezone.utc)
        self.story.pids, self.story.teams = set(), set()  # Status Report identifies through linked full names.
        self.story.en = {8482122: "Brock Faber", 8478445: "Mathew Barzal"}
        self.story.text = (
            "## **Minnesota Wild**\n\n"
            "Brock Faber will make his season debut for the Wild against the Boston Bruins on Saturday "
            "(7 p.m. ET; Wild+, MINNHL, NESN). The defenseman has not played after sustaining a skull fracture "
            "on Sept. 25 in a preseason game against the Dallas Stars.\n\n"
            "## **New York Islanders**\n\nMathew Barzal is day to day.")
        names = {"8482122": {"ru": "Брок Фейбер"}}
        teams = {"MIN": "Миннесота"}

        packet = fact_packet.extract(self.story, names, teams, stories.TEAM_EN)

        self.assertIsNotNone(packet)
        claim = packet["claims"][0]
        self.assertEqual((claim["subject"], claim["club"], claim["kind"], claim["date"]),
                         (8482122, "MIN", "expected_debut", "2026-11-14"))
        self.assertEqual(claim["action_timezone"], "America/New_York")
        self.assertEqual(fact_packet.expires_at(packet), "2026-11-15T00:00:00-05:00")
        body = fact_packet.render(packet)
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(self.story), body), [])
        draft = {"date": "2026-11-15", "data": {
            "source_snapshot": fact_packet.snapshot(self.story),
            "event_revision": fact_packet.revision(packet), "expires_at": fact_packet.expires_at(packet)}}
        ready, _ = editorial_lifecycle.classify(draft, "story-faber", datetime(2026, 11, 14, 21, tzinfo=timezone.utc))
        expired, _ = editorial_lifecycle.classify(draft, "story-faber", datetime(2026, 11, 15, 5, tzinfo=timezone.utc))
        self.assertEqual((ready, expired), ("ready", "expired"))

        now = datetime(2026, 11, 15, 0, tzinfo=timezone(timedelta(hours=3)))
        send = Mock(return_value={"ok": True, "result": {"message_id": 929}})

        def deliver(day, kind):
            ok, report = publish.publish(day, ["tg"], send, kind, automatic=True)
            return ok, "; ".join(report)

        with (
                patch.object(stories, "STATE", self.out / "stories_state.json"),
                patch.object(stories, "parse_item", return_value=self.story),
                patch.object(stories, "select", return_value=[self.story]),
                patch.object(stories, "body_text", return_value=(self.story.text, self.story.en)),
                patch.object(stories, "render_story_card", side_effect=self.draw),
                patch.dict("os.environ", {"NEWS_BOT_TOKEN": "offline", "NEWS_CHANNEL": "-100123456"}),
        ):
            stories.process(now, lambda url: {"items": [{"id": self.story.eid}]} if url == stories.FEED else {},
                            names, teams, lambda pids, registry: names,
                            Mock(side_effect=AssertionError("typed debut must not use LLM")),
                            lambda: [], deliver, Mock())
        send.assert_called_once()
        published = json.loads(next(self.out.glob("*_story-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(published["published"], ["tg"])
        self.assertTrue(published["data"]["auto"])
        self.assertEqual(published["data"]["card_spec"]["hero_id"], 8482122)
        self.assertEqual(published["data"]["card_spec"]["teams"], ["MIN"])
        self.assertEqual(story_validation.check(published, "2026-11-15"), [])
