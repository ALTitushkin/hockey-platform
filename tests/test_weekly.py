import copy
import unittest
from urllib.parse import parse_qs, urlparse

from news import guard, weekly


class WeeklyTests(unittest.TestCase):
    players = {"1": {"ru": "Первый Игрок", "surname": "Игрок", "status": "confirmed"},
               "2": {"ru": "Другой Вратарь", "surname": "Вратарь", "status": "confirmed"}}

    def setUp(self):
        self.skater = {"playerId": 1, "gamesPlayed": 3, "goals": 2, "assists": 4, "points": 6, "plusMinus": 2}
        self.goalie = {"playerId": 2, "gamesPlayed": 2, "wins": 1, "shutouts": 1, "saves": 59, "shotsAgainst": 65}
        self.urls = []

    def collect(self, skaters=None, goalies=None):
        def fetch(url):
            self.urls.append(url)
            rows = skaters if "/skater/" in url else goalies
            return {"total": len(rows), "data": rows}
        return weekly.collect("2026-11-02", self.players, fetch)

    def test_previous_calendar_week_and_year_boundary(self):
        self.assertEqual(weekly.period("2026-11-02"), ("2026-10-26", "2026-11-01"))
        self.assertEqual(weekly.period("2027-01-04"), ("2026-12-28", "2027-01-03"))
        self.assertEqual(weekly.period("2024-03-04"), ("2024-02-26", "2024-03-03"))
        for value in ("2026-11-03", "2026-02-30", '2026-11-02" or 1=1', ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                weekly.period(value)

    def test_exact_two_fixed_host_aggregate_queries(self):
        data = self.collect([self.skater], [self.goalie])
        self.assertEqual(len(self.urls), 2)
        for url in self.urls:
            parsed = urlparse(url)
            self.assertEqual((parsed.scheme, parsed.netloc), ("https", "api.nhle.com"))
            query = parse_qs(parsed.query)
            self.assertEqual(query["isAggregate"], ["true"])
            self.assertEqual(query["isGame"], ["true"])
            self.assertEqual(query["limit"], ["-1"])
            self.assertEqual(query["cayenneExp"], [
            'seasonId=20262027 and gameTypeId=2 and gameDate>="2026-10-26" and gameDate<="2026-11-01"'])
        self.assertEqual(data["sources"], self.urls)

    def test_only_registry_players_and_actual_appearances_are_included(self):
        foreign = {**self.skater, "playerId": 999}
        bench = {**self.goalie, "gamesPlayed": 0, "wins": 0, "shutouts": 0, "saves": 0, "shotsAgainst": 0}
        data = self.collect([self.skater, foreign], [bench])
        self.assertEqual([p["pid"] for p in data["skaters"]], [1])
        self.assertEqual(data["goalies"], [])

    def test_all_points_and_weighted_goalie_percentage_pass_guard(self):
        data = self.collect([self.skater], [self.goalie])
        text, facts = weekly.render(data, self.players)
        self.assertIn("6 (2+4), 3 матча", text)
        self.assertIn("отражено 90,8%", text)
        self.assertIn("1 сухой матч", text)
        self.assertIn("26 октября — 1 ноября 2026", text)
        self.assertEqual(guard.check(text, facts, self.players, {}, publish=True), [])
        self.assertEqual(facts["pids"], {1, 2})

    def test_plus_minus_positive_negative_and_zero_keep_their_sign(self):
        for value, expected in ((5, "+5"), (-7, "-7"), (0, "0")):
            with self.subTest(value=value):
                data = self.collect([{**self.skater, "plusMinus": value}], [])
                text, facts = weekly.render(data, self.players)
                self.assertEqual(data["skaters"][0]["plusMinus"], value)
                self.assertIn(f"+/− {expected}", text)
                self.assertEqual(guard.check(text, facts, self.players, {}, publish=True), [])

    def test_missing_or_invalid_plus_minus_is_not_zero(self):
        for value in (None, True, "-2", 1.5):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                self.collect([{**self.skater, "plusMinus": value}], [])
        row = {k: v for k, v in self.skater.items() if k != "plusMinus"}
        with self.assertRaises(RuntimeError):
            self.collect([row], [])
        data = {"start": "2026-10-26", "end": "2026-11-01", "goalies": [],
                "skaters": [{"pid": 1, **{k: v for k, v in row.items() if k != "playerId"}}]}
        text, _ = weekly.render(data, self.players)
        self.assertIn("+/− н/д", text)

    def test_shutout_in_shootout_loss_does_not_require_a_win(self):
        goalie = {**self.goalie, "gamesPlayed": 1, "wins": 0, "shutouts": 1, "saves": 20, "shotsAgainst": 20}
        data = self.collect([], [goalie])
        text, _ = weekly.render(data, self.players)
        self.assertIn("0 побед", text)
        self.assertIn("100%", text)

    def test_zero_shot_relief_appearance_is_kept_without_percentage(self):
        row = {**self.goalie, "gamesPlayed": 1, "wins": 0, "shutouts": 0, "saves": 0, "shotsAgainst": 0}
        data = self.collect([], [row])
        text, facts = weekly.render(data, self.players)
        self.assertIn("Другой Вратарь", text)
        self.assertIn("без бросков по воротам", text)
        self.assertNotIn("%", text)
        self.assertEqual(guard.check(text, facts, self.players, {}, publish=True), [])

    def test_truncated_or_invalid_response_rejected(self):
        for response in ({}, {"data": []}, {"data": [], "total": 1}, {"data": {}, "total": 0},
                         {"data": [], "total": True}):
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                weekly.collect("2026-11-02", self.players, lambda _url: response)

    def test_missing_or_corrupt_fields_fail_closed(self):
        changes = ({"points": 99}, {"gamesPlayed": 10}, {"gamesPlayed": 0}, {"goals": -1}, {"assists": None},
                   {"points": True}, {"gamesPlayed": "3"})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.collect([{**self.skater, **change}], [])
        for change in ({"wins": 3}, {"shotsAgainst": 2}, {"shutouts": 3}, {"saves": -1}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.collect([], [{**self.goalie, **change}])
        with self.assertRaises(RuntimeError):
            self.collect([self.skater, self.skater], [])
        with self.assertRaises(RuntimeError):
            self.collect([{**self.skater, "playerId": "1"}], [])

    def test_missing_russian_name_is_not_silently_dropped(self):
        players = {"1": {"ru": None, "surname": None}}
        with self.assertRaisesRegex(RuntimeError, "нет русского имени"):
            weekly.collect("2026-11-02", players, lambda _url: {"total": 1, "data": [self.skater]})

    def test_empty_week_has_no_post(self):
        text, facts = weekly.render(self.collect([], []), self.players)
        self.assertEqual(text, "")
        self.assertFalse(facts["pids"])

    def test_all_skaters_in_collapsed_list_and_names_escape_html(self):
        players = copy.deepcopy(self.players)
        players["1"]["ru"] = "Первый & Игрок"
        for pid in range(3, 14):
            players[str(pid)] = {"ru": f"Игрок {pid}", "surname": str(pid), "status": "confirmed"}
        players["4"] = {"ru": "Второй Игрок", "surname": "Игрок", "status": "confirmed"}
        rows = [{"pid": pid, "gamesPlayed": 1, "points": 1, "goals": 1, "assists": 0}
                for pid in (1, *range(3, 14))]
        text, facts = weekly.render({"start": "2026-10-26", "end": "2026-11-01",
                                     "skaters": rows, "goalies": []}, players)
        self.assertIn("&amp;", text)
        self.assertIn("\n\n<blockquote expandable>", text)
        self.assertIn("</blockquote>\n\n", text)
        self.assertEqual(len(facts["pids"]), 12)
        for pid in facts["pids"]:
            self.assertIn(players[str(pid)]["surname"], text)


if __name__ == "__main__":
    unittest.main()
