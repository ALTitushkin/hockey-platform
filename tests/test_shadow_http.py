import io
import unittest

from news.shadow_http import Client, Redirects, Response, validate


class Reply(io.BytesIO):
    def __init__(self, body, url, code=200, headers=None):
        super().__init__(body)
        self.url, self.code, self.headers = url, code, headers or {}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def open(self, request, timeout):
        self.requests.append(request)
        body, code, headers = self.replies.pop(0)
        return Reply(body, request.full_url, code, headers)


class HTTPTests(unittest.TestCase):
    def test_only_fixed_https_hosts_and_same_host_redirects(self):
        for url in ['http://theahl.com/feed', 'https://127.0.0.1/feed', 'https://theahl.com:444/feed',
                    'https://user:password@theahl.com/feed', 'https://theahl.com.evil.test/feed']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate(url)
        import urllib.request
        request = urllib.request.Request('https://theahl.com/feed')
        with self.assertRaises(ValueError):
            Redirects().redirect_request(request, None, 302, '', {}, 'https://www.dailyfaceoff.com/feed')

    def test_robots_ahl_spacing_cache_and_conditional_headers(self):
        now = [100.0]
        waits = []

        def wait(n):
            waits.append(n)
            now[0] += n

        opener = Opener([(b'User-agent: *\nAllow: /\nCrawl-delay: 10', 200, {}),
                         (b'<rss/>', 200, {'ETag': 'v1', 'Last-Modified': 'date'}), (b'', 304, {})])
        state, cache = {}, {}
        client = Client(state, lambda: now[0], wait, opener)
        response = client.poll('https://theahl.com/feed', cache)
        client.accept(response, cache)
        self.assertEqual(client.poll('https://theahl.com/feed', cache).status, 304)
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(waits, [10, 10])
        self.assertEqual(opener.requests[-1].get_header('If-none-match'), 'v1')

    def test_denied_robots_stops_feed_and_future_requests(self):
        opener = Opener([(b'User-agent: *\nDisallow: /feed', 200, {})])
        client, cache = Client({}, lambda: 100, lambda _: None, opener), {}
        for _ in range(2):
            self.assertEqual(client.poll('https://theahl.com/feed', cache).status, 0)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(cache['disabled'], 'robots_denied')

    def test_redirect_target_obeys_cached_robots_policy(self):
        now = [100.0]
        client = Client({}, lambda: now[0], lambda n: now.__setitem__(0, now[0] + n), Opener([]))

        class RedirectingOpener:
            def open(self, request, timeout):
                self.followed = False
                Redirects(client.redirect).redirect_request(
                    request, None, 302, '', {}, 'https://theahl.com/private/feed')
                self.followed = True
                return Reply(b'', request.full_url)

        opener = RedirectingOpener()
        client.opener = opener
        cache = {'robots_until': 1000, 'robots_lines': ['User-agent: *', 'Disallow: /private/']}
        with self.assertRaisesRegex(ValueError, 'redirect_denied_by_robots'):
            client.poll('https://theahl.com/feed', cache)
        self.assertFalse(opener.followed)

    def test_robots_429_retry_after_prevents_next_request(self):
        opener = Opener([(b'', 429, {'Retry-After': '3600'})])
        client, cache = Client({}, lambda: 100, lambda _: None, opener), {}
        with self.assertRaisesRegex(RuntimeError, 'robots_http_429'):
            client.poll('https://theahl.com/feed', cache)
        self.assertEqual(cache['retry_at'], 3700)
        self.assertEqual(client.poll('https://theahl.com/feed', cache).status, 0)
        self.assertEqual(len(opener.requests), 1)

    def test_403_disables_source_and_429_delays_requests(self):
        for code, expected in [(403, 'disabled'), (429, 'retry_at')]:
            opener = Opener([(b'', code, {'Retry-After': '999999999'})])
            client, cache = Client({}, lambda: 100, lambda _: None, opener), {}
            client.poll('https://theahl.com/feed', cache, robots=False)
            self.assertIn(expected, cache)
            self.assertEqual(client.poll('https://theahl.com/feed', cache, robots=False).status, 0)
            self.assertEqual(len(opener.requests), 1)
            if code == 429:
                self.assertEqual(cache['retry_at'], 604900)

    def test_retry_after_two_days_is_not_shortened_to_one_day(self):
        opener = Opener([(b'', 429, {'Retry-After': '172800'})])
        client, cache = Client({}, lambda: 100, lambda _: None, opener), {}
        client.poll('https://theahl.com/feed', cache, robots=False)
        self.assertEqual(cache['retry_at'], 172900)
        self.assertEqual(client.poll('https://theahl.com/feed', cache, robots=False).status, 0)
        self.assertEqual(len(opener.requests), 1)

    def test_oversized_response_rejected(self):
        client = Client({}, lambda: 100, lambda _: None, Opener([(b'12345', 200, {})]))
        with self.assertRaises(ValueError):
            client.get('https://theahl.com/feed', 4)

    def test_large_crawl_delay_skips_request_without_blocking_other_hosts(self):
        opener = Opener([])
        client = Client({'host_requests': {'theahl.com': 100}}, lambda: 101,
                        lambda _: self.fail('must not sleep for hours'), opener)
        with self.assertRaises(RuntimeError):
            client.get('https://theahl.com/feed', 10, delay=86400)
        self.assertEqual(opener.requests, [])

    def test_internal_redirect_is_paced_before_its_http_request(self):
        import urllib.request
        now, waits = [100], []

        def wait(n):
            waits.append(n)
            now[0] += n

        client = Client({}, lambda: now[0], wait, Opener([]))
        client.delays['theahl.com'] = 10
        client.pace('https://theahl.com/feed', 10)
        handler = Redirects(client.redirect)
        request = urllib.request.Request('https://theahl.com/feed')
        redirected = handler.redirect_request(request, None, 301, '', {}, 'https://theahl.com/feed/')
        self.assertEqual(redirected.full_url, 'https://theahl.com/feed/')
        self.assertEqual(waits, [10])
        self.assertEqual(client.state['host_requests']['theahl.com'], 110)

    def test_validators_not_committed_before_parser_acceptance(self):
        cache = {}
        r = Response(200, b'invalid xml', {'ETag': 'broken'})
        self.assertEqual(cache, {})
        Client.accept(r, cache)
        self.assertEqual(cache['etag'], 'broken')
