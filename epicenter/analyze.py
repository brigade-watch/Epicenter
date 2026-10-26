"""Turn raw public activity around one target into an incident report.

Everything here is pure functions over plain dicts, so it can be tested without
network access. The signals are deliberately behavioral (timing, repetition,
where people arrived from). Nothing looks at what side of an issue anyone is on.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---- tunable thresholds (documented in docs/METHODOLOGY.md) ---------------


@dataclass
class Settings:
    bucket_minutes: int = 10           # timeline resolution
    spike_min_events: int = 8          # a bucket needs at least this many events...
    spike_multiplier: float = 4.0      # ...and this many times the baseline to count as a spike
    source_lookback_minutes: int = 120 # a source must be posted this long before a spike, at most
    source_min_overlap: int = 3        # people who engaged with the source AND piled onto the target
    duplicate_similarity: float = 0.75 # Jaccard similarity for "near-identical" text
    duplicate_min_chars: int = 25      # ignore short replies like "lol" or "this"
    duplicate_min_accounts: int = 3    # a duplicate cluster needs this many different accounts...
    duplicate_window_minutes: int = 60 # ...posting it within this window
    early_fraction: float = 0.10       # first 10% of a spike's participants are "early"
    early_min_count: int = 3
    new_account_days: int = 30


@dataclass
class Event:
    kind: str          # reply | quote | link_share
    uri: str
    did: str
    handle: str
    time: float        # unix seconds (when Bluesky indexed it)
    text: str = ""
    engagement: int = 0
    web_url: str = ""


@dataclass
class Incident:
    target: dict
    events: list[Event]
    spikes: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    duplicate_clusters: list[dict] = field(default_factory=list)
    account_signals: dict[str, dict] = field(default_factory=dict)
    timeline: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ---- parsing --------------------------------------------------------------

_FRACTION_RE = re.compile(r"\.(\d+)")


def parse_time(value: str) -> float:
    """Parse AT Protocol timestamps (Z suffix, up to 9 fractional digits) on Python 3.10+."""
    v = value.strip().replace("Z", "+00:00")
    v = _FRACTION_RE.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), v, count=1)
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_from_post(post: dict, kind: str, web_url: str = "") -> Event:
    author = post.get("author", {})
    record = post.get("record", {})
    stamp = post.get("indexedAt") or record.get("createdAt")
    return Event(
        kind=kind,
        uri=post["uri"],
        did=author.get("did", ""),
        handle=author.get("handle", ""),
        time=parse_time(stamp),
        text=(record.get("text") or "")[:500],
        engagement=sum(post.get(k, 0) or 0 for k in ("likeCount", "repostCount", "replyCount", "quoteCount")),
        web_url=web_url,
    )


# ---- timeline & spikes ----------------------------------------------------

def build_timeline(events: list[Event], s: Settings) -> list[dict]:
    if not events:
        return []
    width = s.bucket_minutes * 60
    start = int(min(e.time for e in events) // width * width)
    end = int(max(e.time for e in events) // width * width)
    counts = {t: 0 for t in range(start, end + width, width)}
    for e in events:
        counts[int(e.time // width * width)] += 1
    return [{"t": iso(t), "ts": t, "count": c} for t, c in sorted(counts.items())]


def find_spikes(timeline: list[dict], s: Settings) -> list[dict]:
    if not timeline:
        return []
    counts = [b["count"] for b in timeline]
    nonzero = [c for c in counts if c > 0]
    baseline = max(1.0, statistics.median(nonzero)) if nonzero else 1.0
    threshold = max(s.spike_min_events, baseline * s.spike_multiplier)
    width = s.bucket_minutes * 60
    spikes: list[dict] = []
    for b in timeline:
        if b["count"] < threshold:
            continue
        if spikes and b["ts"] - spikes[-1]["end_ts"] <= width:  # merge adjacent buckets
            spikes[-1]["end_ts"] = b["ts"] + width
            spikes[-1]["events"] += b["count"]
            spikes[-1]["peak"] = max(spikes[-1]["peak"], b["count"])
        else:
            spikes.append({"start_ts": b["ts"], "end_ts": b["ts"] + width,
                           "events": b["count"], "peak": b["count"]})
    for sp in spikes:
        sp["start"], sp["end"] = iso(sp["start_ts"]), iso(sp["end_ts"])
        sp["baseline_per_bucket"] = round(baseline, 1)
    return spikes


# ---- near-duplicate text --------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@[\w.\-]+")
_NONWORD_RE = re.compile(r"[^\w\s]")


def normalize_text(text: str) -> str:
    t = _URL_RE.sub(" ", text.lower())
    t = _MENTION_RE.sub(" ", t)
    t = _NONWORD_RE.sub(" ", t)
    return " ".join(t.split())


def shingles(text: str, n: int = 3) -> set[str]:
    words = text.split()
    if len(words) < n:
        return {text}
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def find_duplicate_clusters(events: list[Event], s: Settings) -> list[dict]:
    items = [(e, normalize_text(e.text)) for e in events]
    items = [(e, t) for e, t in items if len(t) >= s.duplicate_min_chars]
    sh = [shingles(t) for _, t in items]
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i][0].did != items[j][0].did and jaccard(sh[i], sh[j]) >= s.duplicate_similarity:
                parent[find(i)] = find(j)

    groups: dict[int, list[Event]] = {}
    for i, (e, _) in enumerate(items):
        groups.setdefault(find(i), []).append(e)

    clusters = []
    window = s.duplicate_window_minutes * 60
    for members in groups.values():
        # Common phrases get repeated organically over a day; copy-paste campaigns land
        # close together. Keep only members inside a window where enough accounts posted it.
        members.sort(key=lambda e: e.time)
        keep: set[int] = set()
        for i in range(len(members)):
            j = i
            while j < len(members) and members[j].time - members[i].time <= window:
                j += 1
            if len({e.did for e in members[i:j]}) >= s.duplicate_min_accounts:
                keep.update(range(i, j))
        members = [members[i] for i in sorted(keep)]
        accounts = {e.did for e in members}
        if len(accounts) < s.duplicate_min_accounts:
            continue
        clusters.append({
            "sample_text": members[0].text[:280],
            "accounts": len(accounts),
            "posts": [{"did": e.did, "handle": e.handle, "time": iso(e.time),
                       "url": e.web_url} for e in members],
            "first": iso(members[0].time),
            "last": iso(members[-1].time),
            "span_minutes": round((members[-1].time - members[0].time) / 60, 1),
        })
    clusters.sort(key=lambda c: c["accounts"], reverse=True)
    return clusters


# ---- sources --------------------------------------------------------------

def rank_sources(candidates: list[Event], engagers: dict[str, dict[str, float]],
                 events: list[Event], spikes: list[dict], s: Settings) -> list[dict]:
    """A 'source' is a quote or link-share whose own audience later piled onto the target.

    engagers maps source uri -> {did: time they engaged with the source}.
    """
    participants: dict[str, float] = {}
    for e in events:
        if e.kind == "reply":
            participants[e.did] = min(participants.get(e.did, e.time), e.time)

    out = []
    for src in candidates:
        audience = engagers.get(src.uri, {})
        overlap = [did for did, t_src in audience.items()
                   if did in participants and did != src.did
                   and t_src <= participants[did]]  # saw the source first, then went to the target
        if len(overlap) < s.source_min_overlap:
            continue
        linked_spikes = [i for i, sp in enumerate(spikes)
                         if sp["start_ts"] - s.source_lookback_minutes * 60 <= src.time <= sp["end_ts"]]
        out.append({
            "kind": src.kind,
            "uri": src.uri,
            "url": src.web_url,
            "did": src.did,
            "handle": src.handle,
            "time": iso(src.time),
            "text": src.text[:280],
            "engagement": src.engagement,
            "arrivals": len(overlap),
            "arrival_share": round(len(overlap) / max(1, len(participants)), 3),
            "spikes": linked_spikes,
            "_arrived": overlap,
        })
    out.sort(key=lambda x: x["arrivals"], reverse=True)
    return out


# ---- per-account signals ---------------------------------------------------

def account_signals(events: list[Event], spikes: list[dict], clusters: list[dict],
                    sources: list[dict], profiles: dict[str, dict], s: Settings) -> dict[str, dict]:
    signals: dict[str, dict] = {}

    def add(did: str, handle: str, name: str, evidence: str | None = None) -> None:
        rec = signals.setdefault(did, {"handle": handle, "signals": set(), "evidence": []})
        rec["signals"].add(name)
        if evidence and evidence not in rec["evidence"]:
            rec["evidence"].append(evidence)

    for sp in spikes:
        first_seen: dict[str, Event] = {}
        for e in sorted(events, key=lambda e: e.time):
            if sp["start_ts"] <= e.time < sp["end_ts"] and e.did not in first_seen:
                first_seen[e.did] = e
        n_early = max(s.early_min_count, int(len(first_seen) * s.early_fraction))
        for e in list(first_seen.values())[:n_early]:
            add(e.did, e.handle, "early_amplifier", e.web_url)

    for c in clusters:
        for p in c["posts"]:
            add(p["did"], p["handle"], "duplicate_text", p["url"])

    for src in sources:
        handles = {e.did: e.handle for e in events}
        for did in src["_arrived"]:
            add(did, handles.get(did, ""), "arrived_via_source", src["url"])
        if src["spikes"]:
            add(src["did"], src["handle"], "spike_source", src["url"])

    cutoff_days = s.new_account_days * 86400
    first_time = {}
    for e in events:
        first_time[e.did] = min(first_time.get(e.did, e.time), e.time)
    for did, rec in signals.items():
        created = (profiles.get(did) or {}).get("createdAt")
        if created and 0 <= first_time.get(did, 0) - parse_time(created) < cutoff_days:
            rec["signals"].add("new_account")

    for rec in signals.values():
        rec["signals"] = sorted(rec["signals"])
        rec["evidence"] = rec["evidence"][:5]
    return signals


# ---- top level ------------------------------------------------------------

def analyze(target: dict, events: list[Event], source_candidates: list[Event],
            engagers: dict[str, dict[str, float]], profiles: dict[str, dict],
            s: Settings | None = None) -> Incident:
    s = s or Settings()
    events = sorted(events, key=lambda e: e.time)
    timeline = build_timeline(events, s)
    spikes = find_spikes(timeline, s)
    clusters = find_duplicate_clusters([e for e in events if e.kind in ("reply", "quote")], s)
    sources = rank_sources(source_candidates, engagers, events, spikes, s)
    signals = account_signals(events, spikes, clusters, sources, profiles, s)

    participants = {e.did for e in events}
    new_accounts = sum(1 for did, rec in signals.items() if "new_account" in rec["signals"])
    coordinated = bool(spikes) and bool(clusters or any(src["spikes"] for src in sources))

    for src in sources:
        src.pop("_arrived", None)

    return Incident(
        target=target,
        events=events,
        spikes=spikes,
        sources=sources,
        duplicate_clusters=clusters,
        account_signals=signals,
        timeline=[{"t": b["t"], "count": b["count"]} for b in timeline],
        summary={
            "events": len(events),
            "participants": len(participants),
            "spikes": len(spikes),
            "sources": len(sources),
            "duplicate_clusters": len(clusters),
            "flagged_new_accounts": new_accounts,
            "assessment": "coordination signals present" if coordinated
            else ("spike without clear coordination" if spikes else "no unusual activity"),
        },
    )
