"""Metadata-only replay of the six runtime cases audited on 2026-11-07."""

import unittest
from datetime import datetime, timezone

from news.editorial_lifecycle import classify


class LegacyQueueReplay(unittest.TestCase):
    def test_six_historical_tasks_never_acquire_publication_permission(self):
        cases = (("2026-10-26", "league", "expired"),
                 ("2026-10-28", "story-1e8db3b8", "legacy_review"),
                 ("2026-11-04", "story-7ec5e001", "legacy_review"),
                 ("2026-11-06", "story-71095b1f", "legacy_review"),
                 ("2026-11-06", "story-cd2bee5f", "legacy_review"),
                 ("2026-11-06", "story-de4f621c", "legacy_review"))
        for day, kind, expected in cases:
            with self.subTest(kind=kind):
                draft = {"date": day, "data": {}, "issues": []}
                status, reasons = classify(draft, kind, datetime(2026, 11, 7, 18, tzinfo=timezone.utc))
                self.assertEqual(status, expected)
                self.assertTrue(reasons)


if __name__ == "__main__":
    unittest.main()
