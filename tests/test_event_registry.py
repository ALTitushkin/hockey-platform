import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from news import event_registry as er
from news import stories


class EventRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.sqlite3"

    def story(self, headline, text, kind="signing", pid=1):
        return stories.Story(headline, headline, headline, "", datetime(2026, 11, 4, tzinfo=timezone.utc),
                             kind, {pid}, {"NYI"}, True, text=text)

    def pto(self):
        return er.extract(self.story("Islanders sign Hutton to PTO", "Hutton signed a PTO on Monday."))

    def test_same_pto_different_article_same_revision(self):
        a = self.pto()
        b = er.extract(self.story("Hutton Looking To Maximize PTO Opportunity",
                                  "At practice on Tuesday, Hutton, who signed a PTO on Monday, joined the Islanders."))
        self.assertTrue(er.complete(a))
        self.assertTrue(er.complete(b))
        self.assertEqual(a["effective_date"], "2026-11-02")
        self.assertEqual(er.revision_key(a), er.revision_key(b))

    def test_pto_and_full_contract_are_not_duplicates(self):
        a = self.pto()
        b = er.extract(self.story("Islanders sign Hutton to one-year contract",
                                  "Hutton signed a one-year, $1.5 million contract on Wednesday."))
        self.assertTrue(er.complete(b))
        self.assertNotEqual(er.revision_key(a), er.revision_key(b))
        self.assertEqual(b["facts"]["years"], 1)
        self.assertEqual(b["facts"]["amounts"], ["1500000"])

    def test_age_and_career_length_do_not_become_contract_term(self):
        for lead in ("The 33-year-old Player signed a PTO on Monday.",
                     "The eight-year veteran Player signed a PTO on Monday."):
            with self.subTest(lead=lead):
                event = er.extract(self.story("Club signs Player to PTO", lead))
                self.assertTrue(er.complete(event))
                self.assertEqual(event["facts"], {})
                self.assertEqual(er.revision_key(event), er.revision_key(self.pto()))

    def test_new_full_contract_in_headline_is_not_old_pto_from_lead(self):
        event = er.extract(self.story("Club signs Player to one-year contract after PTO",
                                      "Player, previously on a PTO, signed a one-year contract on Wednesday."))
        self.assertTrue(er.complete(event))
        self.assertEqual(event["phase"], "standard")

    def test_contract_money_representation_is_normalized(self):
        a = er.extract(self.story("Player signs one-year contract",
                                  "Player signed a one-year, $1.50 million contract on Wednesday."))
        b = er.extract(self.story("Player signs one-year contract",
                                  "Player signed a one-year, $1,500,000 contract on Wednesday."))
        self.assertEqual(er.revision_key(a), er.revision_key(b))

    def test_injury_diagnosis_duration_and_activation_are_distinct(self):
        events = [er.extract(self.story(h, t, kind)) for h, t, kind in (
            ("Player leaves with upper-body injury", "Player left on Monday and did not return.", "injury"),
            ("Player out two to four weeks", "Club announced on Monday: upper-body injury, two to four weeks.",
             "injury"),
            ("Player out with concussion", "Club announced on Monday that Player has a concussion.", "injury"),
            ("Player activated from injured reserve", "Club announced on Wednesday that Player is activated.",
             "return"),
        )]
        self.assertTrue(all(er.complete(e) for e in events))
        self.assertEqual(len({er.revision_key(e) for e in events}), 4)
        self.assertEqual(events[1]["facts"]["duration"], {"min": 2, "max": 4, "unit": "week"})

    def test_changed_facts_same_phase_create_update(self):
        a = er.extract(self.story("Player out two weeks", "Club announced on Monday: two weeks.", "injury"))
        b = er.extract(self.story("Player out four weeks", "Club announced on Monday: four weeks.", "injury"))
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        db.register("a", "a", a, {})
        self.assertEqual(db.classify(b)["status"], "update")
        self.assertNotEqual(er.revision_key(a), er.revision_key(b))

    def test_unknown_date_or_actors_requires_review_not_identity_guess(self):
        source = self.story("Player signs PTO", "Player joined practice.")
        a = er.extract(source)
        self.assertFalse(er.complete(a))
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        self.assertEqual(db.classify(a)["status"], "review")
        source.pids = {1, 2}
        source.text = "Players signed PTOs on Monday."
        self.assertFalse(er.complete(er.extract(source)))

    def test_return_forecast_is_not_confirmed_return(self):
        event = er.extract(self.story("Player could return on Wednesday",
                                     "Club announced on Wednesday that Player could return.", "return"))
        self.assertFalse(er.complete(event))

    def test_shared_player_and_report_head_do_not_suppress_new_news(self):
        a = self.story("Player signs PTO", "A")
        b = self.story("Player signs standard contract", "B")
        self.assertFalse(stories.same_event(a, b))
        state = {"report_heads": {"Player": "2026-11-04T00:00:00+00:00"}}
        self.assertFalse(stories.report_repeat(b, state, b.date))

    def test_new_medical_facts_outside_repeated_lead_are_not_silently_deduplicated(self):
        source = self.story("Player out with upper-body injury",
                            "Player was injured on Monday.\n\nClub now reports a concussion and four weeks out.",
                            "injury")
        event = er.extract(source)
        self.assertFalse(er.complete(event))
        self.assertTrue(any("вне вводного" in reason for reason in event["reasons"]))

    def test_reservation_persists_and_receipt_recovers_after_json_write_crash(self):
        event = self.pto()
        db = er.Registry(self.path)
        self.assertEqual(db.reserve(event, "tg:@channel", "first.json")[0], "new")
        db.close()
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        self.assertEqual(db.reserve(event, "tg:@channel", "other.json")[0], "uncertain")
        self.assertEqual(db.classify(event)["status"], "review")
        db.finish(event, "tg:@channel", True, [50])
        self.assertEqual(db.reserve(event, "tg:@channel", "first.json"), ("done_own", [50]))
        self.assertEqual(db.reserve(event, "tg:@channel", "other.json")[0], "duplicate")
        self.assertEqual(db.classify(event)["status"], "duplicate")
        self.assertEqual(db.reserve(event, "tg:@different", "other.json")[0], "new")

    def test_resolve_requires_explicit_outcome_and_audit_note(self):
        event = self.pto()
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        db.reserve(event, "tg:@channel", "first")
        db.finish(event, "tg:@channel", False, [])
        with self.assertRaises(ValueError):
            db.resolve(event, "tg:@channel", sent=False, messages=[], note="")
        db.resolve(event, "tg:@channel", sent=False, messages=[], note="Operator checked channel history")
        self.assertEqual(db.reserve(event, "tg:@channel", "second")[0], "new")
        db.resolve(event, "tg:@channel", sent=True, messages=[51], note="Found actual sent message")
        self.assertEqual(db.reserve(event, "tg:@channel", "second")[0], "done_own")

    def test_backlink_does_not_date_a_different_injury(self):
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        db.register("old", "old-injury", self.pto(), {})
        event = er.extract(self.story("Player signs PTO", "Player returned to practice."))
        result = db.bind_reference(event, "https://www.nhl.com/news/old-injury")
        self.assertEqual(result["effective_date"], event["effective_date"])
        self.assertFalse(er.complete(result))

    def test_identity_changes_with_club_actor_date_but_not_evidence_text(self):
        a = self.pto()
        for field, value in (("clubs", ["SEA"]), ("actors", [2]), ("effective_date", "2026-11-03")):
            b = copy.deepcopy(a)
            b[field] = value
            self.assertNotEqual(er.revision_key(a), er.revision_key(b))
        b = {**a, "references": ["a"], "reasons": []}
        self.assertEqual(er.revision_key(a), er.revision_key(b))

    def test_malformed_phase_in_frozen_receipt_does_not_crash_import(self):
        db = er.Registry(self.path)
        self.addCleanup(db.close)
        for phase in ([], {}, None, 5):
            event = {**self.pto(), "phase": phase}
            self.assertFalse(er.complete(event))
            path = self.path.parent / "2026-11-04_story-bad.json"
            path.write_text(json.dumps({"data": {"event_revision": event},
                                        "event_receipts": {"tg": {"event": event, "channel": "tg:-10012345"}}}),
                            encoding="utf-8")
            db.sync_archive(self.path.parent)
        self.assertEqual(db.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)

    def test_incidental_biography_date_does_not_date_contract(self):
        event = er.extract(self.story("Player signs PTO", "Player was born 2000-01-01 and now has a PTO."))
        self.assertFalse(er.complete(event))
        self.assertEqual(event["date_basis"], "publication")


if __name__ == "__main__":
    unittest.main()
