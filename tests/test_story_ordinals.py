"""Живой отказ гарда 01.11: seventh-round pick сопоставляется с цифрой7."""
import unittest
from datetime import datetime, timezone

from news import stories


class OrdinalTests(unittest.TestCase):
    def test_poirier_seventh_round_is_allowed_but_eighth_is_not(self):
        story = stories.Story("poirier", "capitals-acquire-remi-poirier-from-new-jersey", "Capitals acquire Poirier",
                              "", datetime(2026, 11, 1, tzinfo=timezone.utc), "trade", set(), set(), False,
                              text="Washington acquired Poirier for their seventh-round pick in the 2027 NHL Draft.")
        issues, _ = stories.check("Вашингтон получил вратаря за выбор в 7-м раунде драфта 2027 года",
                                 story, {}, {}, {"WSH": "Вашингтон"}, set())
        self.assertEqual(issues, [])
        issues, _ = stories.check("Вашингтон получил вратаря за выбор в 8-м раунде драфта 2027 года",
                                 story, {}, {}, {"WSH": "Вашингтон"}, set())
        self.assertTrue(any("8" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
