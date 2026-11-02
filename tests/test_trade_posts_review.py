import unittest
from datetime import datetime, timezone

from news import stories


class TradePostReviewTests(unittest.TestCase):
    def trade_fixture(self):
        source = stories.Story('trade', 'trade', 'Predators acquire Wright from Kraken for Wood', '',
                               datetime(2026, 11, 1, tzinfo=timezone.utc), 'trade', {1, 2}, {'NSH', 'SEA'}, True)
        names = {'1': {'ru': 'Шейн Райт', 'surname': 'Райт'},
                 '2': {'ru': 'Мэттью Вуд', 'surname': 'Вуд'}}
        teams = {'NSH': 'Нэшвилл', 'SEA': 'Сиэтл'}
        return source, names, teams

    def test_season_tracker_is_not_a_new_trade(self):
        self.assertIsNone(stories.parse_item({'slug': '2026-27-nhl-trades'}))

    def test_single_trade_article_is_not_filtered_with_season_tracker(self):
        article = {'_entityId': 'single-trade', 'slug': 'kraken-trade-wright-to-predators-for-wood',
                   'headline': 'Kraken trade Wright to Predators for Wood', 'summary': '',
                   'contentDate': '2026-11-01T12:00:00Z', 'tags': [{'slug': 'nhl-created'}]}
        parsed = stories.parse_item(article)
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.eid, parsed.kind), ('single-trade', 'trade'))

    def test_balanced_club_quotes_and_explicit_trade_direction_pass_guard(self):
        source, names, teams = self.trade_fixture()
        for text in ('«Нэшвилл» получил Райта из «Сиэтла»\n\nВзамен «Сиэтл» получил Вуда.',
                     '«Сиэтл» отдал Райта в «Нэшвилл»\n\nВзамен клуб получил Вуда.'):
            with self.subTest(text=text):
                cleaned = stories.clean(text)
                self.assertEqual(cleaned, text)
                issues, _ = stories.check(cleaned, source, names, {}, teams, set())
                self.assertEqual(issues, [])

    def test_unbalanced_club_quotes_cannot_pass_guard(self):
        source, names, teams = self.trade_fixture()
        for text in ('«Нэшвилл получил Райта\n\nВзамен «Сиэтл» получил Вуда.',
                     'Нэшвилл» получил Райта\n\nВзамен «Сиэтл» получил Вуда.',
                     'Сиэтл» обменял Райта в «Нэшвилл\n\nСиэтл получил Вуда.'):
            with self.subTest(text=text):
                issues, _ = stories.check(text, source, names, {}, teams, set())
                self.assertIn('несбалансированные кавычки', issues)

    def test_club_quotes_survive_cleaning(self):
        text = '«Сиэтл» обменял Райта в «Нэшвилл»\n\nВ обратном направлении отправился Вуд.'
        self.assertEqual(stories.clean(text), text)

    def test_ambiguous_acquisition_cannot_pass_as_disposal(self):
        source = stories.Story('trade', 'trade', 'Capitals acquire Poirier', '',
                               datetime(2026, 11, 1, tzinfo=timezone.utc), 'trade', set(), set(), True)
        for line in ('Вашингтон обменял Пуарье на выбор драфта', 'Нэшвилл обменял Райта у Сиэтла'):
            issues, _ = stories.check(line, source, {}, {}, {}, set())
            self.assertTrue(any('неясное направление' in issue for issue in issues))


if __name__ == '__main__':
    unittest.main()
