"""Turn an approved watch-request issue into a watchlist entry.

Run by .github/workflows/approve-watch.yml when a maintainer adds the
`approved` label to a `watch-request` issue. The issue text is untrusted
input, so it is only parsed here: never executed, and never pasted into a
shell command.

Edit the issue title to a short, neutral description before approving; it
becomes the public note shown on the site.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .bluesky import POST_URL_RE

WATCHLIST = Path("config/watchlist.json")
URL_RE = re.compile(r"https://[^\s<>()\"'`]{4,500}")
TRACK_DAYS = 14


def parse_sections(body: str) -> dict[str, str]:
    """Split a GitHub issue-form body ('### Heading' then text) into sections."""
    sections: dict[str, str] = {}
    current = None
    for line in (body or "").splitlines():
        if line.startswith("### "):
            current = line[4:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return {k: v.strip() for k, v in sections.items()}


def extract_target(body: str) -> dict | None:
    link = parse_sections(body).get("Link", "")
    m = URL_RE.search(link)
    if not m:
        return None
    url = m.group(0).rstrip(".,;")
    if "bsky.app/profile/" in url:
        post = POST_URL_RE.match(url)
        if not post:
            return None
        return {"type": "bluesky_post", "url": post.group(0)}
    return {"type": "url", "url": url}


def note_from_title(title: str, number: int) -> str:
    note = re.sub(r"^\s*watch\s*:\s*", "", title or "", flags=re.I).strip()
    note = " ".join(note.split())[:120]
    return note or f"Watch request #{number}"


def add_to_watchlist(target: dict, note: str, number: int, path: Path = WATCHLIST,
                     today: str | None = None) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = data.setdefault("targets", [])
    if any(t.get("url") == target["url"] for t in targets):
        return "duplicate"
    targets.append({
        **target,
        "note": note,
        "added": today or datetime.now(timezone.utc).date().isoformat(),
        "track_days": TRACK_DAYS,
        "request": number,
    })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return "added"


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event["issue"]
    note = note_from_title(issue.get("title", ""), issue["number"])
    target = extract_target(issue.get("body") or "")
    result = add_to_watchlist(target, note, issue["number"]) if target else "invalid"
    print(f"{result}: {target['url'] if target else '(no valid link)'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"result={result}\n")
            f.write(f"note={note}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
