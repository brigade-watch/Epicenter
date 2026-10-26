"""Run with: python -m unittest"""

import tempfile
import time
import unittest
from pathlib import Path

from epicenter.analyze import (Event, Settings, find_duplicate_clusters, find_spikes,
                                   build_timeline, parse_time, rank_sources)
from epicenter.scoring import public_accounts, record_incident
from epicenter.store import HistoryStore

T0 = 1_760_000_000.0
S = Settings()


def ev(n, t, text="", kind="reply"):
    return Event(kind, f"at://did:x:{n}/p/{t}", f"did:x:{n}", f"u{n}.example", T0 + t, text, 0, "")


class Parsing(unittest.TestCase):
    def test_atproto_timestamps(self):
        self.assertEqual(parse_time("2024-01-01T00:00:00Z"), 1704067200.0)
        self.assertAlmostEqual(parse_time("2024-01-01T00:00:00.123456789Z"), 1704067200.123456, 5)


class Spikes(unittest.TestCase):
    def test_burst_is_a_spike_and_trickle_is_not(self):
        trickle = [ev(i, i * 900) for i in range(40)]           # one every 15 min
        burst = [ev(100 + i, 20_000 + i * 20) for i in range(30)]  # 30 in 10 minutes
        self.assertEqual(find_spikes(build_timeline(trickle, S), S), [])
        spikes = find_spikes(build_timeline(trickle + burst, S), S)
        self.assertEqual(len(spikes), 1)
        self.assertGreaterEqual(spikes[0]["events"], 30)


class Duplicates(unittest.TestCase):
    TEXT = "Everyone can see what you are doing here and it is not working"

    def test_copy_paste_burst_clusters(self):
        posts = [ev(i, i * 60, self.TEXT + ("!" * i)) for i in range(4)]
        clusters = find_duplicate_clusters(posts, S)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["accounts"], 4)

    def test_same_phrase_spread_over_a_day_does_not(self):
        posts = [ev(i, i * 6 * 3600, self.TEXT) for i in range(4)]
        self.assertEqual(find_duplicate_clusters(posts, S), [])

    def test_short_replies_ignored(self):
        posts = [ev(i, i, "ratio") for i in range(10)]
        self.assertEqual(find_duplicate_clusters(posts, S), [])


class Sources(unittest.TestCase):
    def test_audience_overlap_identifies_source(self):
        src = ev(999, 0, "go look at this", kind="quote")
        events = [ev(i, 600 + i * 10) for i in range(10)]
        engagers = {src.uri: {f"did:x:{i}": T0 + 100 for i in range(6)}}
        ranked = rank_sources([src], engagers, events, [], S)
        self.assertEqual(ranked[0]["arrivals"], 6)

    def test_engaging_after_the_target_is_not_arrival(self):
        src = ev(999, 0, kind="quote")
        events = [ev(i, 600) for i in range(10)]
        engagers = {src.uri: {f"did:x:{i}": T0 + 5000 for i in range(10)}}
        self.assertEqual(rank_sources([src], engagers, events, [], S), [])


class Scoring(unittest.TestCase):
    def sig(self, *names):
        return {"did:x:1": {"handle": "u1.example", "signals": list(names), "evidence": []}}

    def test_threshold_and_weak_signals(self):
        hist = {}
        now = T0 + 10 * 86400
        record_incident(hist, "a", "t1", "2025-10-09T00:00:00Z", self.sig("early_amplifier"))
        record_incident(hist, "b", "t2", "2025-10-09T00:00:00Z", self.sig("duplicate_text"))
        self.assertEqual(public_accounts(hist, set(), parse_time, now), [])   # only 2 incidents
        record_incident(hist, "c", "t3", "2025-10-09T00:00:00Z", self.sig("new_account"))
        self.assertEqual(public_accounts(hist, set(), parse_time, now), [])   # weak signal alone ignored
        record_incident(hist, "d", "t4", "2025-10-09T00:00:00Z", self.sig("early_amplifier"))
        self.assertEqual(len(public_accounts(hist, set(), parse_time, now)), 1)
        self.assertEqual(public_accounts(hist, {"did:x:1"}, parse_time, now), [])  # exclusion honored

    def test_old_incidents_age_out(self):
        hist = {}
        for i in range(4):
            record_incident(hist, str(i), f"t{i}", "2025-01-01T00:00:00Z", self.sig("duplicate_text"))
        self.assertEqual(public_accounts(hist, set(), parse_time, parse_time("2025-12-01T00:00:00Z")), [])


class Store(unittest.TestCase):
    def test_encrypted_history_hides_accounts(self):
        from epicenter.store import generate_key
        with tempfile.TemporaryDirectory() as d:
            store = HistoryStore(Path(d), key=generate_key())
            store.save({"did:plc:someone": {"handle": "someone.example", "incidents": {}}})
            raw = (Path(d) / "history.enc").read_bytes()
            self.assertNotIn(b"someone", raw)
            self.assertIn("did:plc:someone", store.load())
            self.assertNotIn("someone", store.ref("did:plc:someone"))


if __name__ == "__main__":
    unittest.main()
