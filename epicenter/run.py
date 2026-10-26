"""Collect, analyze, and write the public data files the site reads.

    python -m epicenter.run                 # real run against the watchlist
    python -m epicenter.run --demo          # synthetic data into demo-data/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .analyze import Incident, Settings, analyze, iso, parse_time
from .collect import Collected
from .scoring import LABELS, public_accounts, record_incident
from .store import HistoryStore


def incident_id(target: dict) -> str:
    return hashlib.sha256(target["url"].encode()).hexdigest()[:10]


def active(target: dict, today: date) -> bool:
    added = date.fromisoformat(target.get("added", today.isoformat()))
    return (today - added).days <= int(target.get("track_days", 14))


def public_incident(inc: Incident, inc_id: str, ref_if_listed, notes: list[str]) -> dict:
    """The public view of an incident: sources and patterns.

    Accounts appear only as an opaque ref, and only if they are publicly listed.
    Unlisted accounts get no ref and no timestamps, so their posts can't be
    matched back to them from the public thread.
    """
    flagged = [ref_if_listed(did) for did in sorted(inc.account_signals)]
    return {
        "id": inc_id,
        "analyzed_at": iso(time.time()),
        "target": inc.target,
        "summary": inc.summary,
        "notes": notes,
        "timeline": inc.timeline,
        "spikes": [{k: v for k, v in sp.items() if not k.endswith("_ts")} for sp in inc.spikes],
        "sources": [{k: v for k, v in src.items() if k != "did"} for src in inc.sources],
        "duplicate_clusters": [
            {**{k: v for k, v in c.items() if k != "posts"},
             "listed": sorted({r for r in (ref_if_listed(p["did"]) for p in c["posts"]) if r})}
            for c in inc.duplicate_clusters
        ],
        "listed": sorted({r for r in flagged if r}),
        "unlisted_flagged": sum(1 for r in flagged if not r),
    }


def sparkline(timeline: list[dict], points: int = 60) -> list[int]:
    """Downsample a timeline for the list view, keeping peaks (max per slice)."""
    counts = [b["count"] for b in timeline]
    if len(counts) <= points:
        return counts
    step = len(counts) / points
    return [max(counts[int(i * step):max(int(i * step) + 1, int((i + 1) * step))]) for i in range(points)]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def process(collected: list[tuple[str, Collected]], data_dir: Path, store: HistoryStore,
            exclusions: set[str], settings: Settings) -> None:
    history = store.load()
    analyzed = []
    for inc_id, c in collected:
        inc = analyze(c.target, c.events, c.source_candidates, c.engagers, c.profiles, settings)
        for did in [d for d in inc.account_signals if d in exclusions]:
            inc.account_signals.pop(did)
        when = iso(max((e.time for e in inc.events), default=time.time()))
        record_incident(history, inc_id, c.target["url"], when, inc.account_signals)
        analyzed.append((inc_id, inc, c.notes))
        print(f"  {inc_id}: {inc.summary['assessment']} "
              f"({inc.summary['events']} events, {inc.summary['spikes']} spikes, {inc.summary['sources']} sources)")
    store.save(history)

    accounts = public_accounts(history, exclusions, parse_time)
    listed_dids = {a["did"] for a in accounts}
    public = [{"ref": store.ref(a.pop("did")), **a} for a in accounts]

    def ref_if_listed(did: str) -> str | None:
        return store.ref(did) if did in listed_dids else None

    for inc_id, inc, notes in analyzed:
        write_json(data_dir / "incidents" / f"{inc_id}.json", public_incident(inc, inc_id, ref_if_listed, notes))
    write_json(data_dir / "accounts.json", {"generated_at": iso(time.time()), "labels": LABELS,
                                            "accounts": public})

    incidents = []
    for f in sorted((data_dir / "incidents").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        incidents.append({"id": d["id"], "target": d["target"], "summary": d["summary"],
                          "analyzed_at": d["analyzed_at"], "spark": sparkline(d["timeline"]),
                          "first_spike": d["spikes"][0]["start"] if d["spikes"] else None})
    incidents.sort(key=lambda d: d["first_spike"] or d["analyzed_at"], reverse=True)
    write_json(data_dir / "index.json", {"generated_at": iso(time.time()),
                                         "incidents": incidents, "public_accounts": len(public)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="use synthetic data (no network)")
    ap.add_argument("--data", type=Path, help="output folder (default: data/, or demo-data/ with --demo)")
    ap.add_argument("--watchlist", type=Path, default=Path("config/watchlist.json"))
    ap.add_argument("--exclusions", type=Path, default=Path("config/exclusions.json"))
    args = ap.parse_args(argv)

    data_dir = args.data or Path("demo-data" if args.demo else "data")
    exclusions = set()
    if args.exclusions.exists():
        exclusions = set(json.loads(args.exclusions.read_text(encoding="utf-8")).get("dids", []))

    if args.demo:
        from .sample import demo_targets
        store = HistoryStore(data_dir, key="", local_dir=data_dir / ".local")
        collected = [(incident_id(c.target), c) for c in demo_targets()]
        print(f"Demo run -> {data_dir}/")
        process(collected, data_dir, store, exclusions, Settings())
        return 0

    from .bluesky import Bluesky, BlueskyError
    from .collect import collect

    store = HistoryStore(data_dir)
    if not store.encrypted:
        print("HISTORY_KEY not set: keeping account history in .local/ (fine for local testing).")
    watch = json.loads(args.watchlist.read_text(encoding="utf-8")).get("targets", [])
    today = datetime.now(timezone.utc).date()
    bsky = Bluesky()
    print(f"Bluesky: {'signed in' if bsky.authenticated else 'public API (link search may be unavailable)'}")

    collected = []
    for target in watch:
        if not active(target, today):
            continue
        print(f"Collecting {target['url']}")
        try:
            collected.append((incident_id(target), collect(bsky, target)))
        except BlueskyError as e:
            print(f"  skipped: {e}", file=sys.stderr)
    process(collected, data_dir, store, exclusions, Settings())
    return 0


if __name__ == "__main__":
    sys.exit(main())
