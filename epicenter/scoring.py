"""Account track records: how often an account shows up in coordination patterns.

Guardrails baked in here (see docs/METHODOLOGY.md):
- An account only appears publicly after MIN_INCIDENTS separate incidents
  (different targets) inside WINDOW_DAYS. Joining one pile-on never lists anyone.
- Old incidents fade with a half-life, so behavior that stops drops off.
- "new_account" and "arrived_via_source" never count on their own; they only add
  weight next to a stronger signal.
- Accounts removed after a dispute review (config/exclusions.json) are never listed.
"""

from __future__ import annotations

import time

WEIGHTS = {
    "duplicate_text": 2.0,      # near-identical wording to other accounts
    "spike_source": 1.5,        # posted the thing that a spike arrived from
    "early_amplifier": 1.0,     # among the first in at the start of a spike
    "arrived_via_source": 0.5,  # came over from a source post
    "new_account": 0.5,         # account under 30 days old at the time
}
STRONG = {"duplicate_text", "spike_source", "early_amplifier"}

HALF_LIFE_DAYS = 90
WINDOW_DAYS = 180
MIN_INCIDENTS = 3

TIERS = [  # (minimum gauge, neutral label)
    (70, "Very frequent coordination pattern"),
    (40, "Frequent coordination pattern"),
    (0, "Repeated coordination pattern"),
]

LABELS = {
    "duplicate_text": "Near-identical wording to other accounts",
    "spike_source": "Posted the source of a pile-on",
    "early_amplifier": "Among the first to arrive in a spike",
    "arrived_via_source": "Arrived from a source post",
    "new_account": "Account was under 30 days old",
}


def incident_weight(signals: list[str]) -> float:
    if not STRONG.intersection(signals):
        return 0.0
    return sum(WEIGHTS.get(sig, 0.0) for sig in signals)


def record_incident(accounts: dict, incident_id: str, target_key: str, when: str,
                    signals: dict[str, dict]) -> None:
    """Merge one incident's per-account signals into the running history."""
    for did, rec in signals.items():
        if not STRONG.intersection(rec["signals"]):
            continue
        hist = accounts.setdefault(did, {"handle": rec["handle"], "incidents": {}})
        if rec["handle"]:
            hist["handle"] = rec["handle"]
        hist["incidents"][incident_id] = {
            "target": target_key,
            "time": when,
            "signals": rec["signals"],
            "evidence": rec["evidence"],
        }


def score_account(hist: dict, now: float, parse_time) -> dict | None:
    recent = []
    for inc_id, inc in hist["incidents"].items():
        age_days = (now - parse_time(inc["time"])) / 86400
        if age_days <= WINDOW_DAYS:
            recent.append((inc_id, inc, age_days))
    targets = {inc["target"] for _, inc, _ in recent}
    if len(targets) < MIN_INCIDENTS:
        return None

    raw = sum(incident_weight(inc["signals"]) * 0.5 ** (age / HALF_LIFE_DAYS) for _, inc, age in recent)
    gauge = round(100 * raw / (raw + 10))  # saturating 0-100, ~50 at raw score 10
    label = next(name for floor, name in TIERS if gauge >= floor)

    counts: dict[str, int] = {}
    for _, inc, _ in recent:
        for sig in inc["signals"]:
            counts[sig] = counts.get(sig, 0) + 1

    recent.sort(key=lambda x: x[1]["time"], reverse=True)
    return {
        "handle": hist["handle"],
        "gauge": gauge,
        "label": label,
        "incidents": len(targets),
        "signal_counts": counts,
        "history": [{"incident": inc_id, **inc} for inc_id, inc, _ in recent[:20]],
    }


def public_accounts(accounts: dict, exclusions: set[str], parse_time, now: float | None = None) -> list[dict]:
    now = now or time.time()
    out = []
    for did, hist in accounts.items():
        if did in exclusions:
            continue
        scored = score_account(hist, now, parse_time)
        if scored:
            out.append({"did": did, **scored})
    out.sort(key=lambda a: a["gauge"], reverse=True)
    return out
