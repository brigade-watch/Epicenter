"""Minimal Bluesky (AT Protocol) client using only the standard library.

Reads public data from the Bluesky AppView. Search (finding posts that share a
link) works best when signed in, so if BSKY_HANDLE and BSKY_APP_PASSWORD are
set, requests go through an authenticated session. Use an *app password*
(Settings -> Privacy and security -> App passwords), never your main password.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

PUBLIC_API = "https://public.api.bsky.app/xrpc/"
AUTH_API = "https://bsky.social/xrpc/"
USER_AGENT = "epicenter/0.1 (+https://github.com/brigade-watch/epicenter)"

POST_URL_RE = re.compile(r"https?://bsky\.app/profile/([^/]+)/post/([A-Za-z0-9]+)")


class BlueskyError(RuntimeError):
    pass


class Bluesky:
    def __init__(self, handle: str | None = None, app_password: str | None = None,
                 min_interval: float = 0.25):
        self.min_interval = min_interval
        self._last = 0.0
        self._token: str | None = None
        self.base = PUBLIC_API
        handle = handle or os.environ.get("BSKY_HANDLE")
        app_password = app_password or os.environ.get("BSKY_APP_PASSWORD")
        if handle and app_password:
            self._login(handle, app_password)

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    # ---- transport -------------------------------------------------------
    def _login(self, handle: str, app_password: str) -> None:
        body = json.dumps({"identifier": handle, "password": app_password}).encode()
        req = urllib.request.Request(
            AUTH_API + "com.atproto.server.createSession", data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise BlueskyError(f"Bluesky login failed ({e.code}); check the app password") from e
        self._token = data["accessJwt"]
        self.base = AUTH_API

    def get(self, method: str, **params: Any) -> dict:
        pairs = []
        for key, value in params.items():
            if value is None:
                continue
            for item in (value if isinstance(value, list) else [value]):
                pairs.append((key, item))
        query = urllib.parse.urlencode(pairs)
        url = f"{self.base}{method}?{query}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        for attempt in range(5):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(min(60, 2 ** attempt * 2))
                    continue
                detail = e.read().decode(errors="replace")[:300]
                raise BlueskyError(f"{method} -> HTTP {e.code}: {detail}") from e
            except urllib.error.URLError:
                time.sleep(2 ** attempt)
        raise BlueskyError(f"{method} failed after retries")

    def paginate(self, method: str, key: str, max_items: int = 2000, **params: Any) -> Iterator[dict]:
        cursor, seen = None, 0
        while seen < max_items:
            data = self.get(method, cursor=cursor, limit=100, **params)
            items = data.get(key, [])
            for item in items:
                yield item
                seen += 1
                if seen >= max_items:
                    return
            cursor = data.get("cursor")
            if not cursor or not items:
                return

    # ---- helpers ---------------------------------------------------------
    def post_url_to_uri(self, url: str) -> str:
        m = POST_URL_RE.match(url.strip())
        if not m:
            raise BlueskyError(f"Not a Bluesky post URL: {url}")
        actor, rkey = m.groups()
        did = actor if actor.startswith("did:") else self.get(
            "com.atproto.identity.resolveHandle", handle=actor)["did"]
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    def get_post(self, uri: str) -> dict:
        posts = self.get("app.bsky.feed.getPosts", uris=[uri]).get("posts", [])
        if not posts:
            raise BlueskyError(f"Post not found (deleted or private): {uri}")
        return posts[0]

    def get_replies(self, uri: str, depth: int = 6) -> list[dict]:
        data = self.get("app.bsky.feed.getPostThread", uri=uri, depth=depth, parentHeight=0)
        out: list[dict] = []

        def walk(node: dict) -> None:
            for child in node.get("replies") or []:
                if child.get("$type", "").endswith("threadViewPost") and "post" in child:
                    out.append(child["post"])
                    walk(child)

        walk(data.get("thread", {}))
        return out

    def get_quotes(self, uri: str, max_items: int = 2000) -> list[dict]:
        return list(self.paginate("app.bsky.feed.getQuotes", "posts", max_items, uri=uri))

    def get_likes(self, uri: str, max_items: int = 3000) -> list[dict]:
        return list(self.paginate("app.bsky.feed.getLikes", "likes", max_items, uri=uri))

    def search_links(self, url: str, max_items: int = 1000) -> list[dict]:
        """Posts that link to `url`. Usually requires an authenticated session."""
        return list(self.paginate("app.bsky.feed.searchPosts", "posts", max_items,
                                  url=url, sort="latest"))

    def get_profiles(self, dids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(dids), 25):
            batch = dids[i:i + 25]
            for p in self.get("app.bsky.actor.getProfiles", actors=batch).get("profiles", []):
                out[p["did"]] = p
        return out


def web_url(uri: str, handle: str | None = None) -> str:
    """at://did/app.bsky.feed.post/rkey -> https://bsky.app/profile/did/post/rkey"""
    parts = uri.removeprefix("at://").split("/")
    return f"https://bsky.app/profile/{handle or parts[0]}/post/{parts[-1]}"
