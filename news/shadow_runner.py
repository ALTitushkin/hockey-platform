"""Независимый семидневный shadow-сбор: serve / tick / report / health."""
import argparse
import json
import math
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

from news.shadow_http import NHL_FEED, Client
from news.source_dedup import Ledger
from news.source_shadow import SOURCES, parse_feed

INTERVAL, DURATION = 900, 7 * 86400
OUT = Path(__file__).parent / 'out'


def save(path, state):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class Pilot:
    def __init__(self, out=OUT, clock=time.time, wait=time.sleep, client=None):
        self.out, self.clock = Path(out), clock
        self.out.mkdir(parents=True, exist_ok=True)
        self.path = self.out / 'shadow_state.json'
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            # Corrupt state must fail closed: never silently start another seven days.
            if not all(type(self.state.get(k)) in (int, float) and math.isfinite(self.state[k])
                       for k in ('started_at', 'ends_at', 'next_at')):
                raise ValueError('Invalid shadow state')
            if self.state['ends_at'] - self.state['started_at'] != DURATION:
                raise ValueError('Invalid shadow state')
        else:
            now = clock()
            self.state = {'started_at': now, 'ends_at': now + DURATION, 'next_at': now,
                          'sources': {}, 'aliases': {}, 'status': 'active'}
            save(self.path, self.state)
        self.client = client or Client(self.state, clock, wait)

    def observe(self, ledger, source, item_id, url, title, text, date, stats, trusted_ids=()):
        from news.source_events import extract_event
        event = extract_event(title, text, date, self.state['aliases'], trusted_ids=trusted_ids)
        known = ledger.db.execute('SELECT 1 FROM documents WHERE source=? AND item_id=?',
                                  (source, item_id)).fetchone()
        result = ledger.observe(source, item_id, url, text, event)
        stats[result.kind] = stats.get(result.kind, 0) + 1
        field = 'identified_events' if event else 'unclustered'
        stats[field] = stats.get(field, 0) + 1
        if result.reason == 'event':
            stats['event_links'] = stats.get('event_links', 0) + 1
            other = ledger.db.execute('SELECT 1 FROM documents WHERE cluster_id=? AND source<>? LIMIT 1',
                                      (result.cluster_id, source)).fetchone()
            clusters = stats.setdefault('cross_source_clusters', [])
            if other and result.cluster_id not in clusters:
                clusters.append(result.cluster_id)
                stats['cross_source_events'] = len(clusters)
        if event and event.facts.get('partial'):
            stats['partial_event_versions'] = stats.get('partial_event_versions', 0) + 1
        if not known:
            stats['documents_seen'] = stats.get('documents_seen', 0) + 1
        if not known and date:
            try:
                published = datetime.fromisoformat(date.replace('Z', '+00:00')).timestamp()
                if published < self.state['started_at']:
                    stats['initial_backfill'] = stats.get('initial_backfill', 0) + 1
                    return
                delay = self.clock() - published
                if delay >= 0:
                    stats['first_seen_delay_seconds_sum'] = stats.get('first_seen_delay_seconds_sum', 0) + delay
                    stats['first_seen_delay_samples'] = stats.get('first_seen_delay_samples', 0) + 1
            except ValueError:
                pass

    def merge_aliases(self, items):
        from news.source_events import build_aliases
        conflicts = set(self.state.get('alias_conflicts', []))
        aliases = self.state['aliases']
        records = [{'tags': [tag]} for item in items for tag in item.get('tags', [])]
        for record in records:
            for name, pid in build_aliases([record]).items():
                if name in aliases and aliases[name] != pid:
                    conflicts.add(name)
                if name in conflicts:
                    aliases.pop(name, None)
                else:
                    aliases[name] = pid
        self.state['alias_conflicts'] = sorted(conflicts)

    def tick(self):
        now = self.clock()
        if now >= self.state['ends_at']:
            self.state['status'] = 'completed'
            save(self.path, self.state)
            return False
        if now < self.state['next_at']:
            return False
        # Persist cadence before network work: restart cannot create a request burst.
        self.state['next_at'] = now + INTERVAL
        self.state['last_tick'] = now
        save(self.path, self.state)
        ledger = Ledger(self.out / 'sources.sqlite', clock=self.clock)
        try:
            for source, url in {'nhl': NHL_FEED, **SOURCES}.items():
                stats = self.state['sources'].setdefault(source, {})
                cache = stats.setdefault('http', {})
                stats['polls'] = stats.get('polls', 0) + 1
                try:
                    r = self.client.poll(url, cache, robots=source != 'nhl')
                    if r.status == 0:
                        stats['status'] = cache.get('disabled', 'backoff')
                        continue
                    if r.status == 304:
                        stats['not_modified'] = stats.get('not_modified', 0) + 1
                    elif r.status == 200:
                        if source == 'nhl':
                            items = json.loads(r.body)['items']
                            self.merge_aliases(items)
                            for item in items[:40]:
                                title = item.get('headline') or ''
                                text = title + '\n' + (item.get('summary') or '')
                                self.observe(ledger, source, item['_entityId'],
                                             f"https://www.nhl.com/news/{item['slug']}", title, text,
                                             item.get('contentDate', ''), stats,
                                             trusted_ids={int(t['slug'].split('-')[1]) for t in item.get('tags', [])
                                                          if t.get('slug', '').startswith('playerid-')
                                                          and t['slug'].split('-')[1].isdigit()})
                        else:
                            for item in parse_feed(source, r.body):
                                self.observe(ledger, source, item.item_id, item.url, item.title, item.text,
                                             getattr(item, 'published_at', ''), stats)
                        self.client.accept(r, cache)
                    else:
                        raise RuntimeError(f'http_{r.status}')
                    stats['status'], stats['last_ok'] = 'ok', self.clock()
                    stats.pop('error', None)
                except InterruptedError:
                    return False
                except Exception as e:
                    stats['errors'] = stats.get('errors', 0) + 1
                    stats['status'], stats['error'] = 'error', type(e).__name__
                finally:
                    save(self.path, self.state)
        finally:
            ledger.close()
        return True


def serve(out=OUT, clock=time.time):
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    def wait(seconds):
        if stop.wait(seconds):
            raise InterruptedError('shutdown')

    pilot = Pilot(out, clock, wait)
    print('shadow: started (RSS metadata only, no publishing)', flush=True)
    while not stop.is_set():
        pilot.tick()
        if pilot.state['status'] == 'completed':
            print('shadow: seven-day pilot completed', flush=True)
            return
        stop.wait(max(1, min(60, pilot.state['next_at'] - clock())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['serve', 'tick', 'report', 'health'])
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    if args.command == 'serve':
        serve(args.out)
    elif args.command == 'tick':
        Pilot(args.out).tick()
    else:
        state = json.loads((args.out / 'shadow_state.json').read_text(encoding='utf-8'))
        if args.command == 'health':
            age = time.time() - state.get('last_tick', state['started_at'])
            healthy = state.get('status') == 'completed' or age < 1800
            raise SystemExit(0 if healthy else 1)
        print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
