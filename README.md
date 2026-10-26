# Epicenter

A free, open-source tool that traces where online pile-ons come from, using public data
only. It watches posts, finds sudden spikes in replies, works out which other posts sent
people there, spots copy-pasted replies, and keeps a behavior-only track record of
accounts that do this repeatedly.

- **Behavior, not opinions.** Scores come from timing, repetition, and where people
  arrived from. Nothing looks at viewpoints.
- **No unmasking.** Public posts only; no guessing who runs an account.
- **High bar to be named.** An account is listed only after 3 separate incidents in 6
  months, and every score links to its evidence. Everyone else stays a count.

How it decides all of this is in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

**Status:** early. Bluesky is supported. Reddit, YouTube, and manual reports for platforms
without open data (X, Facebook, TikTok) are next.

## Try it locally

Needs Python 3.10+.

```bash
pip install -r requirements.txt
python -m unittest                                   # run the tests
python -m epicenter.run --demo                   # build synthetic demo data
python -m epicenter.preview --data demo-data     # open http://localhost:8000
```

The demo uses invented accounts (handles ending in `.example`).

## Deploy for free on GitHub Pages

1. **Create the repo** on GitHub under the `brigade-watch` organization, named
   `epicenter`, **public**, with no README (this repo already has one).

2. **Turn on Pages.** Repo → Settings → Pages → Source: **GitHub Actions**.

3. **Add the history key.** Generate one locally:

   ```bash
   python -m epicenter.keygen
   ```

   Repo → Settings → Secrets and variables → Actions → New repository secret, named
   `HISTORY_KEY`. This encrypts the history of accounts that aren't publicly listed.
   **Keep a copy somewhere safe**; if it's lost, that history can't be read and starts over.

4. **(Recommended) Add a Bluesky login** so the tool can search for posts that share a link.
   Use a separate Bluesky account for the project, then create an **app password** in
   Bluesky (Settings → Privacy and security → App passwords). Add secrets `BSKY_HANDLE` and
   `BSKY_APP_PASSWORD`. Never use your main password.

5. **Push this folder:**

   ```bash
   git init -b main
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/brigade-watch/epicenter.git
   git push -u origin main
   ```

The workflow in `.github/workflows/collect.yml` runs every 6 hours (or from the Actions
tab with "Run workflow"), commits updated `data/` as `github-actions[bot]`, and publishes
the site at `https://brigade-watch.github.io/epicenter/`.

## Watching a post

Add it to `config/watchlist.json` and push:

```json
{
  "targets": [
    {
      "type": "bluesky_post",
      "url": "https://bsky.app/profile/someone.bsky.social/post/3kxyz...",
      "note": "Short neutral description of the post",
      "added": "2026-10-26",
      "track_days": 14
    }
  ]
}
```

`type` can also be `url` for any link (an article, a video). That tracks where the link is
being shared on Bluesky.

Keep `note` neutral ("Post about the city council vote"), not an accusation.

### Approving suggestions from visitors

Visitors suggest posts with the **Watch request** issue form (linked from the site). To
approve one:

1. Check the link and the reason. Don't approve posts submitted to target the people who
   reply to them.
2. Edit the issue title to a short, neutral description. It becomes the public note.
3. Add the `approved` label.

The **Approve watch request** workflow then adds it to the watchlist, starts a collection
run, comments, and closes the issue. Only people with triage access or above can add
labels, so only maintainers can approve.

First-time setup: Actions tab → **Approve watch request** → **Run workflow** once to
create the `watch-request`, `approved`, and `dispute` labels.

## Handling disputes

Disputes arrive as issues using the **Dispute a listing** form. Check the evidence links on
the account's card. If the listing is wrong, add the account's ID (`did:plc:...`, shown on
the person's Bluesky profile URL or via
`https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle=HANDLE`) to
`config/exclusions.json` and push.

## Layout

```
epicenter/       collector, analysis, scoring, encrypted history
site/            static front end (no build step)
data/            published results (written by the workflow)
config/          watchlist and dispute exclusions
docs/            methodology
tests/           unit tests (python -m unittest)
```

## License

MIT
