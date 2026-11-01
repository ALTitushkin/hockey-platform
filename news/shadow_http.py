"""Ограниченный HTTP-клиент теневого пилота: фиксированные HTTPS endpoints."""
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from news.nhl import UA
from news.source_shadow import SOURCES

NHL_FEED = 'https://forge-dapi.d3.nhle.com/v2/content/en-us/stories?$limit=40'
HOSTS = {urlsplit(u).hostname for u in [*SOURCES.values(), NHL_FEED]}


def html_response(body):
    prefix = body.lstrip(b'\xef\xbb\xbf \r\n\t').lower()
    return prefix.startswith((b'<html', b'<!doctype html'))


def validate(url, host=None):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password
            or p.port not in (None, 443) or (host and p.hostname != host)):
        raise ValueError('URL outside shadow allowlist')
    return p.hostname


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, on_redirect=None):
        self.on_redirect = on_redirect

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate(newurl, validate(req.full_url))
        if self.on_redirect:
            self.on_redirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict


class Client:
    def __init__(self, state, clock=time.time, wait=time.sleep, opener=None):
        self.state, self.clock, self.wait = state, clock, wait
        self.delays = {}
        self.policy = None
        self.opener = opener or urllib.request.build_opener(Redirects(self.redirect))

    def pace(self, url, delay):
        host = validate(url)
        last = self.state.setdefault('host_requests', {}).get(host, 0)
        pause = last + delay - self.clock()
        if pause > 60:
            # Do not violate a long crawl-delay or block all other sources waiting for it.
            raise RuntimeError('host_wait_exceeds_tick_budget')
        if pause > 0:
            self.wait(pause)
        self.state['host_requests'][host] = self.clock()

    def redirect(self, url):
        if self.policy is not None and not self.policy.can_fetch(UA, url):
            raise ValueError('redirect_denied_by_robots')
        self.pace(url, self.delays.get(validate(url), 10 if validate(url) == 'theahl.com' else 1))

    def get(self, url, limit, delay=0, headers=None, policy=None):
        host = validate(url)
        self.policy = policy  # robots.txt itself is fetched without a content policy.
        self.delays[host] = delay
        self.pace(url, delay)
        req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
        try:
            response = self.opener.open(req, timeout=12)
        except urllib.error.HTTPError as e:
            response = e
        with response as r:
            validate(r.geturl(), host)
            body = r.read(limit + 1)
            if len(body) > limit:
                raise ValueError('HTTP response exceeds shadow limit')
            return Response(r.code, body, dict(r.headers))

    def poll(self, url, cache, robots=True):
        host = validate(url)
        if cache.get('disabled'):
            return Response(0, b'', {})
        if self.clock() < cache.get('retry_at', 0):
            return Response(0, b'', {})
        delay = 10 if host == 'theahl.com' else 1
        if robots:
            if self.clock() >= cache.get('robots_until', 0) or 'robots_lines' not in cache:
                r = self.get(f'https://{host}/robots.txt', 65536, delay)
                if r.status != 200:
                    self.retry_after(r, cache)
                    if r.status == 403:
                        cache['disabled'] = 'robots_http_403'
                    raise RuntimeError(f'robots_http_{r.status}')
                if html_response(r.body):
                    cache['disabled'] = 'robots_html_challenge'
                    return Response(0, b'', {})
                lines = r.body.decode('utf-8').splitlines()
                cache['robots_lines'] = lines
                cache['robots_until'] = self.clock() + 86400
            parser = RobotFileParser()
            parser.parse(cache['robots_lines'])
            if not parser.can_fetch(UA, url):
                cache['disabled'] = 'robots_denied'
                return Response(0, b'', {})
            cache['crawl_delay'] = max(delay, parser.crawl_delay(UA) or 0)
            delay = cache.get('crawl_delay', delay)
        headers = {}
        for field, name in [('etag', 'If-None-Match'), ('modified', 'If-Modified-Since')]:
            if cache.get(field):
                headers[name] = cache[field]
        r = self.get(url, 2 * 1024 * 1024, delay, headers, parser if robots else None)
        if r.status == 403:
            cache['disabled'] = 'feed_http_403'
        if r.status == 200 and html_response(r.body):
            cache['disabled'] = 'feed_html_challenge'
            return Response(0, b'', {})
        self.retry_after(r, cache)
        return r

    def retry_after(self, response, cache):
        if response.status == 429:
            lower = {k.lower(): v for k, v in response.headers.items()}
            retry = lower.get('retry-after', '900')
            try:
                seconds = float(retry)
            except ValueError:
                try:
                    seconds = parsedate_to_datetime(retry).timestamp() - self.clock()
                except (ValueError, TypeError):
                    seconds = 900
            # Дольше срока пилота всё равно не обращаемся к источнику.
            cache['retry_at'] = self.clock() + max(900, min(7 * 86400, seconds))

    @staticmethod
    def accept(response, cache):
        headers = {k.lower(): v for k, v in response.headers.items()}
        for key, header in [('etag', 'etag'), ('modified', 'last-modified')]:
            cache[key] = headers.get(header, '')
