"""Замечания редактора отправляют шаблонный или повторяющийся текст на ручное ревью."""
import unittest

from news.stories import editorial_notes


class EditorialTests(unittest.TestCase):
    def test_new_detail_is_not_a_repeat(self):
        self.assertEqual(editorial_notes("Миннесота вызвала Мэйсона Шоу\n\nВ АХЛ он набрал 10 очков."), [])

    def test_repeated_headline_requires_review(self):
        self.assertIn("первое предложение повторяет заголовок", editorial_notes(
            "Миннесота вызвала Мэйсона Шоу\n\nМиннесота вызвала Мэйсона Шоу из фарм-клуба."))

    def test_empty_cliche_requires_review(self):
        self.assertTrue(editorial_notes("Новый контракт\n\nВремя покажет, как сыграет команда."))
