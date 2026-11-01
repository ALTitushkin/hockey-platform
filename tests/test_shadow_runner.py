import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from news.shadow_http import Response
from news.shadow_runner import DURATION, INTERVAL, Pilot
from news.source_dedup import Event, Ledger


class FakeClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def poll(self, url, cache, robots=True):
        self.calls.append(url)
        if 'forge-dapi' in url:
            return Response(200, b'{"items": []}', {})
        if 'dailyfaceoff' in url and self.fail:
            raise RuntimeError('offline')
        return Response(200, b'<rss><channel><item><title>News</title><guid>1</guid>'
                        b'<link>https://theahl.com/story</link></item></channel></rss>', {})

    def accept(self, response, cache):
        cache['accepted'] = True


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out, self.now = Path(self.tmp.name), [100.0]
        self.clock = lambda: self.now[0]
        # Matcher contract is independently tested by its owner.
        module = types.ModuleType('news.source_events')
        module.extract_event = lambda *_, **kwargs: None
        module.build_aliases = lambda _: {}
        self.stub = patch.dict('sys.modules', {'news.source_events': module})
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.tmp.cleanup()

    def test_restart_preserves_deadline_and_cadence(self):
        client = FakeClient()
        pilot = Pilot(self.out, self.clock, client=client)
        self.assertTrue(pilot.tick())
        deadline = pilot.state['ends_at']
        again = Pilot(self.out, self.clock, client=client)
        self.assertFalse(again.tick())
        self.assertEqual(again.state['ends_at'], deadline)
        self.assertEqual(len(client.calls), 3)
        self.now[0] += INTERVAL
        self.assertTrue(again.tick())
        self.assertEqual(again.state['sources']['ahl']['duplicate'], 2)

    def test_expiry_is_normal_completion_without_network(self):
        client = FakeClient()
        pilot = Pilot(self.out, self.clock, client=client)
        self.now[0] += DURATION
        self.assertFalse(pilot.tick())
        self.assertEqual(pilot.state['status'], 'completed')
        self.assertEqual(client.calls, [])

    def test_failure_isolated_and_state_persisted(self):
        pilot = Pilot(self.out, self.clock, client=FakeClient(fail=True))
        pilot.tick()
        self.assertEqual(pilot.state['sources']['dfo']['errors'], 1)
        self.assertEqual(pilot.state['sources']['ahl']['status'], 'ok')
        self.assertEqual(json.loads(pilot.path.read_text())['next_at'], 100 + INTERVAL)

    def test_corrupt_state_does_not_restart_pilot(self):
        (self.out / 'shadow_state.json').write_text('{"started_at":100}')
        with self.assertRaises(ValueError):
            Pilot(self.out, self.clock)

    def test_no_publishing_or_model_calls(self):
        with patch('news.publish.tg_call') as telegram, patch('news.llm.ask') as model:
            Pilot(self.out, self.clock, client=FakeClient()).tick()
        telegram.assert_not_called()
        model.assert_not_called()

    def test_alias_collision_stays_blacklisted_across_polls_and_restart(self):
        pilot = Pilot(self.out, self.clock, client=FakeClient())
        def record(pid):
            return {'tags': [{'name': 'same name', 'pid': pid}]}

        with patch('news.source_events.build_aliases',
                   side_effect=lambda rows: {t['name']: t['pid'] for t in rows[0]['tags']}):
            pilot.merge_aliases([record(1)])
            pilot.merge_aliases([record(2)])
            self.assertNotIn('same name', pilot.state['aliases'])
            pilot.tick()  # persists alias_conflicts
            again = Pilot(self.out, self.clock, client=FakeClient())
            again.merge_aliases([record(1)])
            self.assertNotIn('same name', again.state['aliases'])
            self.assertEqual(again.state['alias_conflicts'], ['same name'])

    def test_identified_event_links_and_first_source_latency_are_distinct(self):
        pilot = Pilot(self.out, self.clock, client=FakeClient())
        ledger = Ledger(':memory:', clock=self.clock)
        event = Event(('player:1',), 'return', '1970-01-01', {'status': 'expected', 'partial': True})
        stats = {}
        with patch('news.source_events.extract_event', return_value=event):
            for source, item in [('nhl', '1'), ('dfo', '2'), ('dfo', '2')]:
                pilot.observe(ledger, source, item, 'https://theahl.com/story', 'Title', 'Text',
                              '1970-01-01T00:00:00+00:00', stats)
        ledger.close()
        self.assertEqual(stats['identified_events'], 3)
        self.assertEqual(stats['event_links'], 2)
        self.assertEqual(stats['partial_event_versions'], 3)
        self.assertEqual(stats['documents_seen'], 2)
        self.assertEqual(stats['initial_backfill'], 2)
        self.assertNotIn('first_seen_delay_samples', stats)
        self.assertEqual(stats['cross_source_events'], 1)
