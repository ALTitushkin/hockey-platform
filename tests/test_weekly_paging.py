from unittest import TestCase

from news.weekly import summary_rows


class WeeklyPagingTests(TestCase):
    def test_api_limit_restarts_with_stable_pages(self):
        url = "https://api.nhle.com/stats/rest/en/skater/summary?start=0&limit=-1"
        all_rows = [{"playerId": i} for i in range(1, 102)]

        def fetch(request):
            if "limit=-1" in request:
                return {"total": 101, "data": all_rows[:100]}
            self.assertIn("sort=playerId", request)
            return {"total": 101, "data": all_rows[100:] if "start=100" in request else all_rows[:100]}

        self.assertEqual(summary_rows(url, "skater", fetch), all_rows)
