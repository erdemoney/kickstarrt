---
title: InfiniDysk
parent: Services
nav_order: 3
---

# InfiniDysk (Usenet streaming gateway)

InfiniDysk is the download and streaming layer: Sonarr and Radarr hand it releases over a
SABnzbd-compatible API, it fetches the article payloads from your Usenet provider, and it hands
the library back as **`.strm` links** — one small text file per episode or movie, holding a URL.
Jellyfin reads those links and streams and seeks the real bytes from your Usenet account, so while
the segment cache is off the media itself never lands on the VPS
([Provider data usage](#provider-data-usage)).

It runs from the media-server stack with the plumbing already in the compose
(`data/infinidysk` → `/config`, `/mnt/usenet` bind-mounted) — nothing to add, and no FUSE, no
rclone sidecar, no host port. It keeps the stack-wide `no-new-privileges` hardening because it
needs no privileges to serve files.

## First run: one step

`just init` seeds the settings; the **admin account is the one thing env config cannot set**.
Visit `https://infinidysk.<DOMAIN>` once, over the tailnet
([Quickstart §9](../quickstart#9-set-up-the-apps)), and create a username and password.

The guided Setup Guide that appears after that first login is optional — every setting it walks
through is already pinned here. Settings whose value comes from Compose are shown **read-only
with a lock badge** naming the variable that owns them; change the variable (or the `.env` behind
it) and restart the container rather than trying to save them in the UI.

## What the stack configures, and why

| Setting (env variable) | Value | Why |
| --- | --- | --- |
| `api.categories` | `tv,movies` | matches the categories `just wire` sets on the Arr download clients |
| `api.import-strategy` | `strm` | Jellyfin playback, no FUSE mount, no symlinks |
| `api.completed-downloads-dir` | `/mnt/usenet/completed-downloads` | where finished releases are staged before import |
| `general.base-url` | `http://infinidysk:3000` | the absolute URL written into each `.strm` file |
| `media.library-dir` | `/mnt/usenet/library` | the library tree health checks walk |
| `repair.enable` | `true` | background health checks over the library |
| `usenet.providers` | your NNTP account | written by `just init` |
| `arr.instances` | Radarr + Sonarr, with API keys and queue rules | written by `just wire` |
| `api.ensure-article-existence-categories` + `api.article-existence-check-mode` | `tv,movies` + `full` | verify a release is complete *before* the Arr is told it downloaded |
| `api.key` | mirrors `.env`'s `INFINIDYSK_API_KEY` | Compose also supplies the key as `FRONTEND_BACKEND_API_KEY`; one key for frontend↔backend auth and for the Arr download clients |

The article-existence check is the one setting worth understanding. With it on, InfiniDysk
statistics every article of a release before reporting success, so a truncated or partially
removed download **fails the grab** and the Arr can blocklist it and search for a replacement,
instead of importing a file that breaks later. The cost is provider traffic and a slower grab.
If that is too slow for your connection, set the check mode to `sampled` — first, last and evenly
spaced segments per file, which still catches most truncation.

The check does **not** try to repair what it finds. PAR2 reconstruction is a post-mount mechanism,
triggered by health checks, streaming failures, and queue rules, so a release with a handful of
missing articles is failed at grab time, the Arr blocklists it and searches for a replacement, and
the parity that could have fixed it is never used. In practice that costs less than it sounds,
because PAR2 repair is itself narrowly scoped: at most **8 missing slices** per recovery, a **16
GiB** source-volume ceiling checked before any content read, **256 MiB** of repair memory, a **4
GiB** patch store, and no more than three provider attempts per job. A 4K remux is typically
40–80 GB, so UHD remuxes sit outside that release-size cap and PAR2 cannot help them at all. The
strict check therefore rejects mostly genuinely dead postings. `sampled` would admit more releases,
but it also misses truncation in the middle of a file — importing media that only breaks once
someone plays it — so it trades false failures for false passes.

One caveat in the other direction: a full sweep is a long in-queue phase, and the stuck-item
watchdog fails an item after three cumulative stalls of five minutes without progress. Raise
`QUEUE_ITEM_STUCK_MINUTES` (commented in `compose.yaml`) before blaming a release if large season
packs start failing in the queue. `queue.worker-count` stays at 1 by design — extra workers share
the same connection pool and add no provider capacity.

Two path invariants come out of the table, and both are satisfied by the compose: the
**completed-downloads directory must exist at the same absolute path inside the \*arrs** (so
Sonarr/Radarr can move a finished release into the library), and the **media server must be able
to reach the base URL** (so Jellyfin can open the link). Every service binds `/mnt/usenet` at that
same path and shares the `internal` network, which is exactly why nothing is published to the
host and no path mapping is ever needed.

## The \*arr side

The download clients themselves are in Sonarr/Radarr; `just wire` creates one named
`InfiniDysk (Usenet)` pointing at `infinidysk:3000`. Its API key is the generated
`INFINIDYSK_API_KEY` from the private `.env` — there is nothing to copy out of the UI. That
is the one credential the Arr download-client form and InfiniDysk must agree on, so if you ever
change it, update the `.env` and re-run `just wire`.

Enable **automatic redownload of failed downloads** in each Arr's download-client settings: when
InfiniDysk rejects a release, that failure is the signal the Arr uses to search for a better one.
`just wire` also registers Radarr and Sonarr in InfiniDysk using the `.env` value
`INFINIDYSK_ARR_INSTANCES`, which Compose passes into the container as
`NZBDAV_CONFIG__ARR__INSTANCES`. This lights up the Overview **Arr health** widget and lets the
queue rules act on stuck imports.

### Automatic queue management

That same JSON carries a `QueueRules` array, written by `just wire`, so the Arr apps never
accumulate queue items that nothing will ever resolve. A rule matches when its `Message` is a
**case-sensitive substring** of the queue record's status text, and when several rules match the
strongest action wins; only records the Arr reports as completed or awaiting import are touched, so
a release that is still downloading is never removed. `Action` is the upstream ordinal: `1` remove,
`2` remove and blocklist, `3` remove, blocklist, and search.

| Reason | Action | Why |
| --- | --- | --- |
| `Sample`, `No audio tracks detected`, `No files found are eligible for import`, `Episode was not found in the grabbed release` | remove, blocklist, search | the release itself is unusable, so get a different one |
| `Not an upgrade for existing episode/movie file`, `Not a Custom Format upgrade` | remove, blocklist | a valid release that lost to what is already imported; don't search again, just stop re-grabbing it |
| `Episode file already imported` | remove | clears the duplicate without recording the upload as rejected |

Everything else is deliberately left at the upstream default of **Do Nothing**, which holds the
record in Awaiting import for you to look at: releases matched by ID, `Invalid season or episode`,
`Single episode file contains all episodes in seasons`, `Found archive file, might need to be
extracted`, and both the `Episode(s) was/were unexpected considering the folder name` and
`Unable to determine if file is a sample` cases. Each of those can still be the right file — a
season-numbering disagreement needs a manual import, and an archive can be a layout InfiniDysk
mounts but the Arr does not unpack. Blocklisting them would throw away a usable release and burn
one of the three replacement searches.

Two things to know about the rules that act. `No files found are eligible for import` is usually a
property of the release, but it is also what a misconfigured completed-downloads path looks like, so
check the shared path in the table above the first time you see it fire repeatedly. And
remove-and-blocklist records article IDs from the rejected download, so a later NZB carrying any of
them is failed before import even under a different release name — which is the point, but it is
why an over-broad rule is expensive.

`just wire` is the only writer of this JSON, so edit the `INFINIDYSK_QUEUE_RULES` list in
`scripts/wire.py` and re-run `just wire`, rather than reaching for the Settings UI. The Arr Apps
page will show these fields **read-only with a "Managed by `NZBDAV_CONFIG__ARR__INSTANCES`" badge**,
and that is the expected result rather than a sign the setting failed to apply: a config key backed
by an environment variable is authoritative, so the UI disables the control to keep it from being
edited into a value the next recreate would discard. There is no separate environment variable for
queue rules to switch to — `arr.instances` is a single config item holding the instances, the rules,
and the replacement-search limits together, so it locks as one unit. `QueueReplacementSearchLimit` /
`QueueReplacementSearchWindowMinutes` live in the same JSON if you want to change the cap from the
upstream default of three searches per media item per 30 minutes.

## Provider data usage

Nothing is stored, so the provider's transfer allowance is consumed by **watching**, not by adding
anything to the library.

| Stage | Provider traffic |
| --- | --- |
| Search | none — the indexer is queried, not Usenet |
| Grab | an article **STAT** sweep of the release plus a head-and-tail **BODY** read of the video: a few MB, and up to 32 MiB for a single read when a whole PAR2 slice must be verified. No copy of the release is made. |
| Playback | the bill — Jellyfin's range requests pull the matching articles on every play, and with the segment cache off there is no local copy, so rewatches and seeks pay again |

Ballpark for a two-hour watch: **5–15 GB** for 1080p WEB, **50–90 GB** for a 4K remux. Pick a
provider allowance to match, bearing in mind the shipped Direct Play profile deliberately prefers
UHD remuxes.

Shared streams (on by default) collapse the probe request and the playback request onto one fetch
and keep a stream briefly warm after the last reader disconnects, but nothing survives that. To
make repeat plays local, uncomment the segment-cache keys in `compose.yaml`; to cap the rate,
uncomment `NZBDAV_CONFIG__USENET__BANDWIDTH_LIMIT_MBPS`. A failed play can add a burst, because
repair fetches source and parity slices to reconstruct what it can — rare, and bounded by the PAR2
limits above.

## Repairs and the database

`repair.enable` plus the library directory gives the background worker something to walk, and
**Remove Orphaned Files** in the Maintenance tab cleans up links whose content is gone. STRM
sidecars under the completed-downloads directory are never treated as library entries, so they
are not reaped. Repair waits for a PAR2 recovery before it gives up on a failing playback.

All of this state — the SQLite database, the session key, and the `repair-segments` patch store —
lives in `data/infinidysk`, so it is covered by the same restic snapshots as the rest of `data/`
([Backups](../maintenance/backups)). Keep `repair-segments` in the backup: it holds the only remaining
copy of any article whose provider copy is gone. NZB backups are a separate, opt-in feature
(`api.nzb-backup-enabled`, off by default).

## Archives

Multi-volume RAR and 7z releases are mounted and streamed from inside the archive, including many
password-protected ones, without extracting the whole set to disk. RAR is parsed lazily, so only
the parts a stream actually touches are decoded, and PAR2 repair works on missing articles inside
RAR releases too.

The one unsupported layout is **RAR volumes stored inside a 7z archive**: those mount as archive
files instead of expanding to the inner video, so an NZB made up only of that layout fails the
`api.ensure-importable-video` media check with an explanation rather than importing nothing. A
mixed release with reachable media still succeeds. Choose a release with top-level media or a
top-level archive.

## Troubleshooting

- **Container restarts and never becomes healthy** — an unknown or miscased `NZBDAV_CONFIG__…`
  name, or a bad property inside the Usenet/Arr JSON, aborts startup with a single-line error that
  names the variable and never prints its value. Fix the variable in the `.env`. A long first-run
  database migration, by contrast, does *not* mark the container unhealthy: the healthcheck targets
  the frontend's `/healthz`.
- **The Arr download client test fails** — check the key in
  `stacks/media-server/.env` matches `NZBDAV_CONFIG__API__KEY`, then
  `docker compose -f stacks/media-server/compose.yaml logs --tail=50 infinidysk`.
- **An import lands but Jellyfin will not play it** — read the URL inside the `.strm` file. It
  must resolve from inside the Jellyfin container; `docker exec jellyfin curl -fsSI <url>` is the
  quickest check.
- **It plays, then dies partway with nothing obviously wrong** — check the container. Matroska
  (`.mkv`) and MPEG-TS (`.ts`) resync past small holes and fast-start or fragmented MP4 usually
  tolerates them, but **moov-at-end MP4 is fatal on any segment loss** and is not covered by the
  degraded-damage tolerance. Re-grab a Matroska source; no setting recovers it.
- **The Usenet provider is unreachable** — the host must be able to reach
  `news.example.net:563` outbound. Try it from the box: `openssl s_client -connect <host>:563`.

## Further reading

- [InfiniDysk getting started](https://www.infinidysk.com/getting-started/) (first run and Docker)
- [Headless configuration](https://www.infinidysk.com/configuration/headless/)
- [Import strategies](https://www.infinidysk.com/guides/import-strategies/)
- [Arr Apps](https://www.infinidysk.com/configuration/arrs/)
