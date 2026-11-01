"""Регрессия поста №36: last5Games не ограничивает действительную серию."""
import unittest

from news import intrigue


def games(count, **stats):
    return [{"gameId": n, "gameDate": f"2026-10-{n:02d}", **stats}
            for n in range(count, 0, -1)]


class StreakTests(unittest.TestCase):
    def test_malformed_game_log_does_not_become_a_publishable_partial_series(self):
        valid = {"gameId": 1, "gameDate": "2026-10-01", "goals": 1, "points": 1}
        malformed_rows = [None, 1, [], {}, {**valid, "gameDate": None},
                          {**valid, "gameDate": "not-a-date"}, {**valid, "gameDate": "2026-02-30"},
                          {**valid, "gameId": "1"}, {**valid, "gameId": True},
                          {**valid, "goals": None}, {**valid, "points": True},
                          {**valid, "points": "1"}, {**valid, "points": -1}]
        roots = [None, [], "error", {}, {"gameTypeId": 2, "gameLog": None},
                 {"gameTypeId": 2, "gameLog": {}},
                 *({"gameTypeId": 2, "gameLog": [valid] * 7 + [row]} for row in malformed_rows)]
        for root in roots:
            with self.subTest(root=root):
                self.assertEqual(intrigue.game_log(1, "C", lambda url: root), [])

    def texts(self, data):
        return [item["text"] for item in intrigue.player_items(8481611, "Игрок", data)]

    def test_post36_goalie_nine_wins_not_last_five(self):
        data = {"position": "G", "gameLog": games(9, decision="W"),
                "last5Games": games(5, decision="W", gameTypeId=2)}
        self.assertEqual(self.texts(data), ["🥅 <b>Игрок</b> — 9 побед подряд"])

    def test_post36_skater_seven_goals_not_last_five(self):
        data = {"position": "C", "gameLog": games(7, goals=1, points=1),
                "last5Games": games(5, goals=1, points=1, gameTypeId=2)}
        self.assertEqual(self.texts(data), ["🔥 <b>Игрок</b> забивает 7 матчей подряд"])

    def test_post36_points_streak_counts_assists(self):
        data = {"position": "D", "gameLog": games(10, goals=0, points=1),
                "last5Games": games(5, goals=0, points=1, gameTypeId=2)}
        self.assertEqual(self.texts(data), ["🔥 <b>Игрок</b> набирает очки 10 матчей подряд"])

    def test_latest_result_stops_streak_even_when_older_games_are_successful(self):
        for position, stats, failure in (("G", {"decision": "W"}, {"decision": "L"}),
                                         ("C", {"goals": 1, "points": 1}, {"goals": 0, "points": 0})):
            with self.subTest(position=position):
                log = games(9, **stats)
                log[0].update(failure)
                self.assertEqual(self.texts({"position": position, "gameLog": log}), [])

    def test_old_failure_bounds_the_current_streak_in_either_api_order(self):
        log = games(10, goals=1, points=1)
        log[6].update(goals=0, points=0)
        for rows in (log, list(reversed(log))):
            self.assertEqual(self.texts({"position": "C", "gameLog": rows}),
                             ["🔥 <b>Игрок</b> забивает 6 матчей подряд"])

    def test_absent_or_empty_log_does_not_guess_from_landing_window(self):
        for position in ("G", "C"):
            for log in ({}, {"gameLog": []}, {"gameLog": None}):
                with self.subTest(position=position, log=log):
                    data = {"position": position, "last5Games": games(
                        5, goals=1, points=1, decision="W", gameTypeId=2), **log}
                    self.assertEqual(self.texts(data), [])

    def test_collect_uses_full_log_and_preserves_career_milestones_on_failure(self):
        for result in (RuntimeError("offline"), {}, {"gameTypeId": 2, "gameLog": []},
                       {"gameTypeId": 3, "gameLog": games(9, decision="W")}):
            calls = []

            def fetch(url):
                calls.append(url)
                if url.endswith("/landing"):
                    return {"position": "G", "careerTotals": {"regularSeason": {"wins": 199}},
                            "last5Games": games(5, decision="W", gameTypeId=2)}
                if isinstance(result, Exception):
                    raise result
                return result

            rows = intrigue.collect({"CAR": [(8481611, "Игрок")]}, fetch)
            self.assertEqual([r["text"] for r in rows], ["🎯 <b>Игрок</b> — одна победа до 200 в НХЛ"])
            self.assertEqual(calls, [f"{intrigue.WEB}/player/8481611/landing",
                                     f"{intrigue.WEB}/player/8481611/game-log/now"])

    def test_collect_long_skater_streak_comes_from_log_not_landing(self):
        def fetch(url):
            if url.endswith("/landing"):
                return {"position": "C", "last5Games": games(5, points=0, goals=0, gameTypeId=2)}
            return {"gameTypeId": 2, "seasonId": 20262027, "gameLog": games(8, goals=0, points=1)}

        rows = intrigue.collect({"CAR": [(8481611, "Игрок")]}, fetch)
        self.assertEqual([r["text"] for r in rows], ["🔥 <b>Игрок</b> набирает очки 8 матчей подряд"])


if __name__ == "__main__":
    unittest.main()
