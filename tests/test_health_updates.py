from datetime import datetime, timezone
from unittest import TestCase

from news import editorial_lifecycle, fact_packet, shadow_extract, stories


class HealthUpdateTests(TestCase):
    def test_numbered_report_span_binds_player_and_match(self):
        evidence = ("Evgeni Malkin\u00a0will not play against the Nashville Predators on Saturday "
                    "(6 p.m. ET; SN-PIT) because of a lower-body injury.")
        story = stories.Story("report", "status", "NHL Status Report: Malkin out", "",
                              datetime(2026, 11, 21, 20, tzinfo=timezone.utc), "injury_minor",
                              set(), set(), True, text=f"## Pittsburgh Penguins\n\n{evidence}\n\nOther details.",
                              en={8471215: "Evgeni Malkin"})
        proposal = {"span_id": 1, "player": "Evgeni Malkin", "club": "Pittsburgh Penguins",
                    "opponent": "Nashville Predators", "action": "match_absence",
                    "modality": "confirmed", "event_date": "2026-11-21"}
        self.assertEqual(shadow_extract.resolve_span(story.text, proposal), evidence)
        self.assertIsNone(shadow_extract.resolve_span(story.text, {"span_id": 99}))
        game = {"id": 2026020362, "homeTeam": {"abbrev": "NSH"}, "awayTeam": {"abbrev": "PIT"},
                "startTimeUTC": "2026-11-21T23:00:00Z"}
        proposal["evidence"] = evidence
        self.assertEqual(shadow_extract.calendar_absence(story, proposal, stories.TEAM_EN, [game])["game_id"],
                         game["id"])
        self.assertIsNone(shadow_extract.calendar_absence(story, {**proposal, "event_date": "2026-11-22"},
                                                        stories.TEAM_EN, [game]))
        packet = fact_packet.extract(story, {"8471215": {"ru": "Евгений Малкин"}},
                                     {"PIT": "Питтсбург"}, stories.TEAM_EN)
        self.assertEqual(fact_packet.expires_at(packet), "2026-11-21T18:00:00-05:00")
        self.assertEqual(fact_packet.verify(packet, fact_packet.snapshot(story), fact_packet.render(packet)), [])

    def packet(self, text):
        story = stories.Story("test", "health-update", "Health update", "",
                              datetime(2026, 11, 21, 21, tzinfo=timezone.utc),
                              "injury", {1}, {"COL"}, True, text=text, en={1: "Test Player"})
        return fact_packet.extract(story, {"1": {"ru": "Игрок"}},
                                   {"COL": "Колорадо"}, stories.TEAM_EN)

    def test_possible_surgery_does_not_become_announced(self):
        lead = ("Test Player will have surgery on his right shoulder, Colorado Avalanche general "
                "manager Test Manager told traveling reporters following a 4-3 win at the Kings on Saturday.")
        self.assertEqual(self.packet(lead)["claims"][0]["kind"], "surgery_announced")
        self.assertIsNone(self.packet(lead.replace("will have", "may have")))

    def test_recovery_keeps_expected_modality(self):
        packet = self.packet("Test Player is expected to be out 12 weeks with a lower-body injury after "
                             "the Colorado Avalanche center was reevaluated by a specialist, "
                             "coach Test Coach said Saturday.")
        self.assertEqual(packet["claims"][0]["modality"], "expected")
        self.assertIn("как ожидается", fact_packet.render(packet))

    def test_absence_expires_at_puck_drop(self):
        packet = self.packet("Test Player will not play for the Colorado Avalanche against the "
                             "Vancouver Canucks on Saturday (10 p.m. ET; SN).")
        start = datetime.fromisoformat(fact_packet.expires_at(packet))
        self.assertEqual(start.isoformat(), "2026-11-21T22:00:00-05:00")
        draft = {"data": {"source_snapshot": {"content_hash": "fixture"},
                          "expires_at": start.isoformat()}}
        self.assertEqual(editorial_lifecycle.classify(draft, "story-test", start)[0], "expired")
