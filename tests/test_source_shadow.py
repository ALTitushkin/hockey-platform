"""RSS-пилот не скачивает вложения и сохраняет версии через общий ledger."""
import unittest

from news.source_shadow import MAX_FEED, parse_feed


class ShadowFeedTests(unittest.TestCase):
    def test_rss_full_body_and_guid(self):
        feed = b'''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
        <guid>story-1</guid><title>Player out 3 weeks</title><link>https://theahl.com/story?utm_source=rss</link>
        <description>Short teaser</description><content:encoded><![CDATA[<p>Confirmed: 3 weeks.</p>]]>
        </content:encoded></item></channel></rss>'''
        item, = parse_feed("ahl", feed)
        self.assertEqual(item.item_id, "story-1")
        self.assertEqual(item.url, "https://theahl.com/story")
        self.assertEqual(item.text, "Player out 3 weeks\nConfirmed: 3 weeks.")

    def test_link_fallback_and_unsafe_links(self):
        feed = b'''<rss><channel><item><title>OK</title><link>https://www.dailyfaceoff.com/news/test</link></item>
        <item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>'''
        item, = parse_feed("dfo", feed)
        self.assertEqual(item.item_id, item.url)

    def test_reject_dtd_utf16_size_and_wrong_format(self):
        samples = [b'<!DOCTYPE rss [<!ENTITY x "expanded">]><rss><channel>&x;</channel></rss>',
                   '<rss><channel/></rss>'.encode('utf-16'), b'x' * (MAX_FEED + 1), b'<html/>']
        for payload in samples:
            with self.subTest(payload=payload[:40]), self.assertRaises(ValueError):
                parse_feed("dfo", payload)

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            parse_feed("unknown", b'<rss><channel/></rss>')


if __name__ == "__main__":
    unittest.main()
