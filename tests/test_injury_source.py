import unittest

from news import injuries, nhl


class InjurySourceTest(unittest.TestCase):
    def test_only_exact_espn_injury_endpoint_is_allowed(self):
        nhl.validate_url(injuries.ESPN)
        for url in (injuries.ESPN + "?other=1", injuries.ESPN + "/other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                nhl.validate_url(url)
