import json
import tempfile
import unittest
from pathlib import Path

from epicenter.approve import add_to_watchlist, extract_target, note_from_title

FORM = """### Link

{link}

### What are you seeing?

Lots of identical replies in ten minutes.

### Before you submit

- [X] The link is public, and I haven't included private information about anyone.
"""


class Parse(unittest.TestCase):
    def test_bluesky_post(self):
        t = extract_target(FORM.format(link="https://bsky.app/profile/a.bsky.social/post/3kabc123?ref=x"))
        self.assertEqual(t, {"type": "bluesky_post", "url": "https://bsky.app/profile/a.bsky.social/post/3kabc123"})

    def test_other_link(self):
        t = extract_target(FORM.format(link="https://example.com/article."))
        self.assertEqual(t, {"type": "url", "url": "https://example.com/article"})

    def test_rejects_non_https_and_bad_bluesky(self):
        self.assertIsNone(extract_target(FORM.format(link="http://example.com")))
        self.assertIsNone(extract_target(FORM.format(link="https://bsky.app/profile/a.bsky.social")))
        self.assertIsNone(extract_target("no form here"))

    def test_link_only_read_from_link_field(self):
        body = FORM.format(link="nothing").replace("Lots of", "https://evil.example Lots of")
        self.assertIsNone(extract_target(body))

    def test_note(self):
        self.assertEqual(note_from_title("Watch:  Post about the  council vote", 4), "Post about the council vote")
        self.assertEqual(note_from_title("Watch: ", 7), "Watch request #7")


class Watchlist(unittest.TestCase):
    def test_add_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.json"
            p.write_text(json.dumps({"targets": []}))
            target = {"type": "url", "url": "https://example.com/a"}
            self.assertEqual(add_to_watchlist(target, "Note", 3, p, today="2026-10-26"), "added")
            self.assertEqual(add_to_watchlist(target, "Note", 4, p), "duplicate")
            saved = json.loads(p.read_text())["targets"]
            self.assertEqual(saved, [{"type": "url", "url": "https://example.com/a", "note": "Note",
                                      "added": "2026-10-26", "track_days": 14, "request": 3}])


if __name__ == "__main__":
    unittest.main()
