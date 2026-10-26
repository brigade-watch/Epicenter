# Methodology

Epicenter measures **behavior**, not opinions. It never looks at what side of an
issue anyone is on, never labels anyone a bot or troll, and never tries to work out who
runs an account.

## What gets collected

For each target in `config/watchlist.json`, using only Bluesky's public API:

| Data | Used for |
|---|---|
| Replies to the post (nested threads included) | Timeline, spikes, copy-paste detection |
| Quote posts of it | Possible sources, timeline |
| Posts sharing its link (needs a signed-in Bluesky session) | Possible sources, timeline |
| Likes and replies on the top 5 quote/share posts | Tracing who arrived from where |
| Account creation dates | The "new account" signal |

Times come from when Bluesky indexed each post, not the timestamp the poster's app
claims, so posts can't be backdated into or out of a spike.

## Signals

**Spike.** Posts are counted in 10-minute buckets. A bucket is a spike when it has at
least 8 posts *and* at least 4× the post's typical (median) bucket. Adjacent spike
buckets merge into one window.

**Source.** A quote post or link share is a source when at least 3 accounts liked or
replied to it *before* posting on the target. "Arrival share" is the fraction of all
accounts on the target that came that way. A source is tied to a spike if it was posted
within 2 hours before that spike started.

**Copy-paste group.** Replies or quotes are compared after removing links, mentions and
punctuation, using overlapping three-word sequences. Two posts match at 75% similarity.
A group needs at least 3 different accounts posting the matching text within 60 minutes.
Posts under 25 characters ("ratio", "this") are ignored.

**Early amplifier.** The first 10% of accounts to post during a spike (at least 3).

**New account.** The account was under 30 days old when it posted.

## From signals to a listing

Each account's signals in an incident get a weight:

| Signal | Weight |
|---|---|
| Near-identical wording | 2.0 |
| Posted the source of a pile-on | 1.5 |
| Among the first in a spike | 1.0 |
| Arrived from a source post | 0.5 |
| New account | 0.5 |

An incident only counts toward an account if it includes at least one of the first three.
Arriving from a source or having a new account never counts on its own.

The gauge adds up incident weights with a **90-day half-life** (an incident three months
old counts half) and maps the total onto 0–100 (`100 × total / (total + 10)`), so it rises
quickly at first and flattens out.

An account is **listed publicly only after 3 separate incidents within 180 days.** Joining
one pile-on, or two, never gets anyone named.

## What is published, and what isn't

Published in `data/`:
- Each incident's timeline, spikes, source posts, and copy-paste groups (the text, how many
  accounts, and how fast)
- Listed accounts, with their gauge and links to the posts behind every incident

Not published:
- Anyone below the listing threshold. Incident pages show them only as a count. Their
  history is stored encrypted (`data/history.enc`), readable only with the `HISTORY_KEY`
  secret, so the public repo can't be mined for who joined a single pile-on.
- Anything not already public on Bluesky. No private messages, no email, no location, no
  guessing at real identities, and no linking accounts across platforms unless the person
  has publicly linked them.

## Known limits

- **Viral is not coordinated.** A post can spike because it's genuinely popular or
  outrageous. That's why a spike alone is reported as "spike without clear coordination".
- **Common phrases.** People really do write the same thing independently, especially
  short reactions. The 60-minute window and minimum length reduce, but don't remove, this.
- **Partial view.** Search results and like lists can be incomplete, deleted posts vanish,
  and Bluesky is one platform of many.
- **Sources show the path, not intent.** Someone can quote-post to criticize and still draw
  a crowd they didn't ask for. The "posted the source" signal only counts toward a listing
  when it repeats across incidents.

## Disputes

Anyone can [open a dispute](../../../issues/new?template=dispute.yml). A maintainer reviews
the evidence links, and if the listing is wrong, adds the account ID to
`config/exclusions.json`. Excluded accounts are never listed again.
