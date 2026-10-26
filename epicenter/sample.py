"""Synthetic demo data, so the site and analysis can be tried without network access.

Every account and post here is invented (handles end in .example).
"""

from __future__ import annotations

import random
import time

from .analyze import Event
from .collect import Collected

PHRASES = [
    "This is exactly why nobody trusts you anymore, delete this post",
    "Imagine posting this and thinking you are on the right side of history",
    "Everyone can see what you are doing here and it is not working",
]
ORGANIC = [
    "Interesting point, though I think the second half is a stretch.",
    "Do you have a source for the numbers in the screenshot?",
    "Ha, this made my morning.",
    "I disagree but appreciate you laying it out clearly.",
    "Saving this for later, good thread.",
    "Not sure this is the whole story, there was a follow-up yesterday.",
]


def _did(n: int) -> str:
    return f"did:example:{n:04d}"


def _handle(n: int) -> str:
    return f"sample-user-{n:03d}.example"


def _url(did: str, rkey: str) -> str:
    return f"https://bsky.app/profile/{did}/post/{rkey}"


def demo_targets(now: float | None = None, seed: int = 7) -> list[Collected]:
    rnd = random.Random(seed)
    now = now or time.time()
    core = list(range(1, 13))          # a small group that shows up in every pile-on
    out = []
    for t_index in range(4):
        t0 = now - (4 - t_index) * 9 * 86400 - 20 * 3600   # targets spread over ~5 weeks
        target_did = _did(900 + t_index)
        events: list[Event] = []
        k = 0

        def add(kind: str, n: int, ts: float, text: str, engagement: int = 0) -> Event:
            nonlocal k
            k += 1
            rkey = f"t{t_index}r{k}"
            ev = Event(kind, f"at://{_did(n)}/app.bsky.feed.post/{rkey}", _did(n), _handle(n),
                       ts, text, engagement, _url(_did(n), rkey))
            events.append(ev)
            return ev

        # organic background: ~40 people over a day
        for _ in range(40):
            add("reply", rnd.randint(200, 800), t0 + rnd.uniform(0, 24 * 3600), rnd.choice(ORGANIC))

        # a quote post 6h in draws a crowd
        source_author = 100 + t_index
        src_time = t0 + 6 * 3600
        src = add("quote", source_author, src_time, "Look at what this account just posted. Go see for yourselves.",
                  engagement=rnd.randint(300, 900))

        crowd = core + list(range(20 + t_index * 50, 20 + t_index * 50 + 40))
        engagers = {}
        phrase = PHRASES[t_index % len(PHRASES)]
        for i, n in enumerate(crowd):
            liked = src_time + rnd.uniform(60, 1500)
            engagers[_did(n)] = liked
            arrive = liked + rnd.uniform(30, 900)
            if n in core and i < 12:
                text = phrase + rnd.choice(["", ".", "!!", " lol"])
                arrive = src_time + 300 + i * 20
            else:
                text = rnd.choice(["Wow.", "Unreal take", "Ratio", "lmao what", "yikes", "Delete this", "big yikes"])
            add("reply", n, arrive, text)

        profiles = {}
        for n in core[:6]:
            profiles[_did(n)] = {"did": _did(n), "createdAt": _iso(t0 - 12 * 86400)}
        for e in events:
            profiles.setdefault(e.did, {"did": e.did, "createdAt": _iso(now - 800 * 86400)})

        out.append(Collected(
            target={"type": "bluesky_post", "url": _url(target_did, f"target{t_index}"),
                    "note": f"Demo target {t_index + 1}", "author_handle": _handle(900 + t_index),
                    "text": "An ordinary post that later drew a pile-on (synthetic demo data).",
                    "posted": _iso(t0), "uri": f"at://{target_did}/app.bsky.feed.post/target{t_index}"},
            events=events,
            source_candidates=[src],
            engagers={src.uri: engagers},
            profiles=profiles,
            notes=["Synthetic demo data — not real accounts."],
        ))
    return out


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))
