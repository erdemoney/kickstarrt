---
title: Indexers
nav_order: 10
---

# Indexers: Prowlarr, self-hosted Comet, and AltHub

Prowlarr is the single place indexers are configured; everything syncs to Sonarr/Radarr via
"Apps" (wired in [The \*arrs](arrs)). Any time after the stack is up
([Quickstart §9](quickstart#9-set-up-the-apps)) — but you need at least one before grabs
work.

## Recommended indexers

| Indexer      | Type               | Cost               | Where it fits                           |
| ------------ | ------------------ | ------------------ | --------------------------------------- |
| Comet (Local) | torrent aggregator | free (self-hosted) | debrid-cached streams through Decypharr |
| AltHub       | Usenet             | $20 lifetime       | Usenet streaming through TorBox         |

Detailed recommendations live in [Services](services).

## Self-hosted Comet

The media stack runs **Comet** (`stacks/media-server/compose.yaml`) — a torrent/debrid
search add-on whose **DMM ingester** imports the public DMM hashlists into its own Postgres
database. It scrapes the same release sources a standalone Torrentio/AioStreams/Debrid.io
would (public DMM + MediaFusion + StremThru, plus optional credentialed scrapers), so it is
the stack's only torrent indexer. It is exposed only on the tailnet:
no public router, no published ports. Its admin dashboard (DMM ingestion progress,
scraper health, cache stats) lives at `https://comet.<DOMAIN>/admin` (the hostname root
redirects there; password set by
`just init`).

**`just wire` registers it for you.** The Cardigann definition
(`data/prowlarr/Definitions/Custom/comet-local.yml`, tracked in git) lives in prowlarr's
`Definitions/Custom` and is mounted in with `/config`, so Prowlarr loads it at startup;
`just wire` then creates the
**Comet (Local)** indexer at the internal-only service URL `http://comet:8000` with
**no API key**, and keeps it re-pointed/enabled on later runs. It syncs to Sonarr/Radarr
like any other indexer — no Prowlarr GUI step needed.

The definition models Comet's **native Torznab API** (`/torznab/api`) with two
category-specific paths. Both pin `t=search`, because Comet only serves its recent
feed for empty-query `search` requests; `movie`/`tvsearch` with an empty query do
not produce the feed needed by Arr validation and RSS. Movie requests pin
`cat=2000`, TV requests pin `cat=5000`, while `q`, `imdbid`, `season`, and `ep` pass
through for explicit searches. The one deviation from Generic Torznab is that
every release title is suffixed `[DEBRID-CACHED]` so the shipped Recyclarr **Direct
Play** profiles can score Comet releases over uncached sources.

The recent feed depends on Comet's newest demand candidates. As a result, an
upstream Comet release whose candidate torrent is classified with season/episode
metadata can miss that movie from the movie recent feed; explicit movie searches
remain unaffected.

Notes:
- **First DMM ingestion is the heavy one**: ~10–30 min of sustained CPU (more on a 2 vCPU box)
  as Comet downloads and indexes the shared hashlists; results are only served after at least
  one ingestion cycle (watch `just logs-svc comet`). Ingestion is **resumable** — if it's
  interrupted (reboot, OOM), the next start picks up where it left off. Later cycles
  (`DMM_INGEST_INTERVAL`, daily) are incremental and light.
- Comet covers the same torrent sources a standalone Torrentio/AioStreams/Debrid.io setup would:
  the public **MediaFusion** (`mediafusion.elfhosted.com`) and **StremThru**
  (`stremthru.13377001.xyz`) instances plus the local **DMM** cache, with a modest **background
  pre-cacher** (single worker, capped runs). Torrentio's own instance is intentionally left off:
  `torrentio.strem.fun` Cloudflare-challenges VPS/datacenter IPs. Credentialed scrapers
  (Debridio, AIOStreams) are wired as env placeholders — fill the keys in
  `stacks/media-server/.env` and enable their `SCRAPE_*` toggles (see `.env.example`).
  AIOStreams' URL is given a non-empty placeholder default because Comet crashes at
  import if it ever sees an empty `AIOSTREAMS_URL`; set the real URL to use it.
- The `Comet (Local)` indexer needs no debrid account and returns cached/debrid-ready releases.
  Its results are marked `[DEBRID-CACHED]` and receive a preference score in the shipped Direct
  Play profiles, while non-Comet results remain eligible for uncached downloads.
- Nyaa and AnimeTosho are enabled by default as free, anime-only Comet scrapers. They do not
  pollute movie or standard TV feeds; set `SCRAPE_NYAA=false` or `SCRAPE_ANIMETOSHO=false` in
  `stacks/media-server/.env` to disable either one.
- Use `{imdbid:tt123456}` (optionally `{season:00}{episode:00}`) for precise hits; a plain-text
  title search resolves through Comet's metadata and may miss very niche titles, falling back to
  fetching its known cache instead.
- On a low-RAM box the initial ingestion may be tight; run it once (e.g. overnight) and let it
  finish before relying on the indexer.

## Adding a regular Usenet indexer (e.g. AltHub)

1. Buy / register (see [Services](services)), then take the **API key + Newznab URL** from the
   indexer's profile page.
2. Prowlarr → Indexers → **+** → **Newznab**: paste the URL and API key, enable, test, save.
3. It syncs to Sonarr/Radarr automatically via the Apps configured earlier. With TorBox Pro and
   Decypharr, the resulting Usenet media is streamed through the debrid mount.
