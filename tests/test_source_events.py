"""Gold-пары теневого matcher: известные факты и неизвестная полнота различаются."""
import unittest

from news.source_dedup import Ledger
from news.source_events import build_aliases, extract_event

ALIASES = {"nikita zadorov": 8477507, "alex vlasic": 8481568, "andre burakovsky": 8477444,
           "sebastian aho": 8478427, "sebastian andersson": 8480001}
WHEN = "2026-11-01T12:00:00Z"


def event(title, text="", when=WHEN, aliases=None):
    trusted = ALIASES if aliases is None else aliases
    return extract_event(title, text, when, trusted, trusted_ids=trusted.values())


class EventMatcherTests(unittest.TestCase):
    def test_rss_incomplete_alias_cache_does_not_make_surname_unique(self):
        aliases = {"john smith": 1}
        self.assertIsNone(extract_event("Smith fined", "", WHEN, aliases))
        full = extract_event("John Smith fined", "", WHEN, aliases)
        self.assertEqual(full.entities, ("player:1",))
        tagged = extract_event("Smith fined", "", WHEN, aliases, trusted_ids={1})
        self.assertEqual(tagged.entities, ("player:1",))
        self.assertIsNone(extract_event("Smith fined", "", WHEN, aliases, trusted_ids={2}))

    def test_aliases_use_only_valid_nhl_player_tags_and_normalize_accents(self):
        items = [{"tags": [{"slug": "playerid-8477507", "title": "Níkita Zadóröv"},
                           {"slug": "teamid-8477507", "title": "Wrong Person"},
                           {"slug": "playerid-7", "title": "Invalid ID"},
                           {"slug": "playerid-8477444", "title": "Burakovsky"}]}]
        self.assertEqual(build_aliases(items), {"nikita zadorov": 8477507})
        self.assertEqual(event("Zadorov fined", aliases=build_aliases(items)).entities, ("player:8477507",))

    def test_conflicting_fullname_tags_do_not_resolve_to_a_random_id(self):
        tags = [{"slug": "playerid-8477507", "title": "Nikita Zadorov"},
                {"slug": "playerid-8477508", "title": "Nikita Zadorov"}]
        aliases = build_aliases([{"tags": tags}])
        self.assertNotIn("nikita zadorov", aliases)
        self.assertIsNone(event("Zadorov fined", aliases=aliases))

    def test_unknown_and_ambiguous_surnames_do_not_match(self):
        aliases = {"sebastian aho": 8478427, "johan aho": 8480002}
        self.assertIsNone(event("Aho recalled", aliases=aliases))
        self.assertIsNone(event("Unknown recalled"))
        self.assertEqual(event("Sebastian Aho recalled", aliases=aliases).entities, ("player:8478427",))

    def test_accented_fullname_and_unique_surname_resolve_same_player(self):
        self.assertEqual(event("Níkita Zadóröv fined").entities, event("Zadorov fined").entities)

    def test_confident_fine_paraphrases_have_same_canonical_facts(self):
        a = event("Zadorov fined $5,000 for roughing Vlasic")
        b = event("Nikita Zadorov fined $5000 for roughing Alex Vlasic")
        self.assertEqual((a.key(), a.facts), (b.key(), b.facts))
        self.assertEqual(a.facts["targets"], [8481568])
        self.assertEqual(a.facts["infraction"], "roughing")
        self.assertNotIn("partial", a.facts)

    def test_fine_amount_change_is_a_new_version_of_same_event(self):
        a = event("Zadorov fined $5,000 for roughing Vlasic")
        b = event("Zadorov fined $10,000 for roughing Vlasic")
        self.assertEqual(a.key(), b.key())
        self.assertNotEqual(a.facts, b.facts)

    def test_fine_additional_numbers_and_negation_are_not_silently_suppressed(self):
        title = "Zadorov fined $5,000 for roughing Vlasic"
        original = event(title)
        for body in ("Nikita Zadorov also faces a suspension of 2 games.",
                     "Nikita Zadorov was not suspended for the incident."):
            with self.subTest(body=body):
                changed = event(title, body)
                self.assertEqual(original.key(), changed.key())
                self.assertNotEqual(original.facts, changed.facts)

    def test_expected_confirmed_and_denied_are_distinct_versions(self):
        events = [event(title) for title in ("Zadorov expected to be fined", "Zadorov fined",
                                             "Zadorov won't be fined")]
        self.assertEqual([e.facts["status"] for e in events], ["expected", "confirmed", "denied"])
        self.assertEqual(len({e.key() for e in events}), 1)
        self.assertEqual(len({str(e.facts) for e in events}), 3)

    def test_changed_actions_and_dates_do_not_merge(self):
        recalled = event("Burakovsky recalled")
        assigned = event("Burakovsky assigned to minors")
        tomorrow = event("Burakovsky recalled", when="2026-11-02T12:00:00Z")
        self.assertEqual((recalled.action, assigned.action), ("recall", "assign"))
        self.assertEqual(len({e.key() for e in (recalled, assigned, tomorrow)}), 3)

    def test_missing_or_invalid_date_does_not_guess_episode(self):
        for when in (None, "", "not-a-date", "2026-02-30T12:00:00Z"):
            with self.subTest(when=when):
                self.assertIsNone(event("Zadorov fined", when=when))

    def test_body_player_is_not_used_as_headline_hero(self):
        self.assertIsNone(event("An unnamed player was fined", "Nikita Zadorov played yesterday."))
        a = event("Zadorov fined", "Burakovsky was injured. Nikita Zadorov was fined.")
        self.assertEqual(a.entities, ("player:8477507",))
        self.assertNotIn("injury_details", a.facts)

    def test_partial_evidence_keeps_paraphrases_as_versions_instead_of_suppressing(self):
        a = event("Burakovsky injured", "Andre Burakovsky will miss two weeks.")
        b = event("Burakovsky sidelined", "Andre Burakovsky is out for two weeks.")
        self.assertEqual(a.key(), b.key())
        self.assertTrue(a.facts["partial"] and b.facts["partial"])
        self.assertEqual(a.facts["duration"], [2, 2, "week"])
        self.assertNotEqual(a.facts["evidence"], b.facts["evidence"])

    def test_ledger_gold_pairs_duplicate_complete_facts_but_update_partial_evidence(self):
        ledger = Ledger(":memory:")
        try:
            cases = [("Zadorov fined $5,000 for roughing Vlasic", "", "new"),
                     ("Nikita Zadorov fined $5000 for roughing Alex Vlasic", "", "duplicate"),
                     ("Zadorov fined $10,000 for roughing Vlasic", "", "update"),
                     ("Burakovsky injured", "Andre Burakovsky is out two weeks.", "new"),
                     ("Burakovsky sidelined", "Andre Burakovsky will miss two weeks.", "update")]
            for n, (title, text, expected) in enumerate(cases):
                with self.subTest(title=title):
                    decision = ledger.observe("source", str(n), f"https://example.com/{n}", title + text,
                                              event(title, text))
                    self.assertEqual(decision.kind, expected)
        finally:
            ledger.close()


if __name__ == "__main__":
    unittest.main()
