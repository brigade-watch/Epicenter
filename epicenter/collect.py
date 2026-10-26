"""Gather everything the analysis needs for one watchlist target from Bluesky."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .analyze import Event, event_from_post, parse_time
from .bluesky import Bluesky, BlueskyError, web_url

MAX_SOURCES = 5            # source posts to trace per target
MIN_SOURCE_ENGAGEMENT = 10 # ignore quotes/shares nobody saw
MAX_PROFILES = 1500


@dataclass
class Collected:
    target: dict
    events: list[Event]
    source_candidates: list[Event]
    engagers: dict[str, dict[str, float]]
    profiles: dict[str, dict]
    notes: list[str]


def _ev(post: dict, kind: str) -> Event:
    return event_from_post(post, kind, web_url(post["uri"], post.get("author", {}).get("handle")))


def collect(bsky: Bluesky, target: dict) -> Collected:
    notes: list[str] = []
    events: list[Event] = []
    info: dict = {"type": target["type"], "url": target["url"], "note": target.get("note", "")}

    if target["type"] == "bluesky_post":
        uri = bsky.post_url_to_uri(target["url"])
        post = bsky.get_post(uri)
        info.update({
            "uri": uri,
            "author_handle": post["author"].get("handle"),
            "text": (post.get("record", {}).get("text") or "")[:500],
            "posted": post.get("indexedAt"),
        })
        events += [_ev(p, "reply") for p in bsky.get_replies(uri)]
        events += [_ev(p, "quote") for p in bsky.get_quotes(uri)]
        share_url = target["url"]
    elif target["type"] == "url":
        share_url = target["url"]
    else:
        raise BlueskyError(f"Unknown target type: {target['type']}")

    try:
        events += [_ev(p, "link_share") for p in bsky.search_links(share_url)]
    except BlueskyError as e:
        notes.append("Link-share search unavailable" + ("" if bsky.authenticated else
                     " (set BSKY_HANDLE and BSKY_APP_PASSWORD to enable it)"))
        print(f"  note: {e}", file=sys.stderr)

    # de-duplicate (a quote can also show up in link search)
    seen, unique = set(), []
    for e in events:
        if e.uri not in seen:
            seen.add(e.uri)
            unique.append(e)
    events = unique

    candidates = sorted((e for e in events if e.kind in ("quote", "link_share")
                         and e.engagement >= MIN_SOURCE_ENGAGEMENT),
                        key=lambda e: e.engagement, reverse=True)[:MAX_SOURCES]

    engagers: dict[str, dict[str, float]] = {}
    for src in candidates:
        audience: dict[str, float] = {}
        try:
            for like in bsky.get_likes(src.uri):
                did = like.get("actor", {}).get("did")
                if did and like.get("createdAt"):
                    audience[did] = min(audience.get(did, 1e18), parse_time(like["createdAt"]))
            for reply in bsky.get_replies(src.uri):
                did = reply["author"]["did"]
                audience[did] = min(audience.get(did, 1e18), parse_time(reply["indexedAt"]))
        except BlueskyError as e:
            notes.append(f"Could not trace one source post ({e})")
        engagers[src.uri] = audience

    dids = list(dict.fromkeys(e.did for e in sorted(events, key=lambda e: e.time)))
    profiles = bsky.get_profiles(dids[:MAX_PROFILES]) if dids else {}

    return Collected(info, events, candidates, engagers, profiles, notes)
