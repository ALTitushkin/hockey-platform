import unittest
from datetime import datetime
from types import SimpleNamespace

from news import event_registry, temporal


class TemporalTests(unittest.TestCase):
    def test_historical_injury_requires_context(self):
        s = SimpleNamespace(date=datetime(2026, 11, 4), en={1: "Igor Shesterkin"},
                            text="Igor Shesterkin, who sustained a season-ending knee injury Oct. 9.")
        names = {"1": {"surname": "Шестёркин"}}
        self.assertTrue(temporal.check("Шестёркин выбыл до конца сезона", s, names))
        for text in ("Шестёркин продолжает пропускать матчи", "Шестёркин выбыл 9 октября",
                     "Шестёркин ранее выбыл до конца сезона"):
            self.assertEqual(temporal.check(text, s, names), [])
        self.assertEqual(temporal.check("Корписало выбыл до конца сезона", s, names), [])
        s.date = datetime(2026, 10, 9)
        self.assertEqual(temporal.check("Шестёркин выбыл до конца сезона", s, names), [])

    def test_unrelated_statistics_are_not_an_injury_date(self):
        s = SimpleNamespace(date=datetime(2026, 11, 4), en={1: "Igor Shesterkin"},
                            text="Igor Shesterkin suffered a knee injury Oct. 9.")
        names = {"1": {"surname": "Шестёркин"}}
        self.assertTrue(temporal.check("Шестёркин выбыл до конца сезона, в 5 матчах он одержал 3 победы", s, names))

    def test_date_in_another_sentence_does_not_belong_to_injured_player(self):
        s = SimpleNamespace(date=datetime(2026, 11, 4), en={1: "Igor Shesterkin"},
                            text="Igor Shesterkin suffered a knee injury. Another player returned Oct. 9.")
        self.assertEqual(temporal.check("Шестёркин выбыл до конца сезона", s,
                                       {"1": {"surname": "Шестёркин"}}), [])

    def test_announcement_today_does_not_override_explicit_signing_day(self):
        story = SimpleNamespace(date=datetime(2026, 11, 6), kind="signing", pids={1}, teams={"NYI"},
                                headline="Club signs Player to one-year contract",
                                text="Club announced today that Player signed a one-year contract on Monday.")
        event = event_registry.extract(story)
        self.assertEqual(event["effective_date"], "2026-11-02")
