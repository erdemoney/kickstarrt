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
scraper health, cache stats) lives at `https://comet.<DOMAIN>`. `just init`
generates a random dashboard password once into the git-ignored `.env`, so no
password is ever committed to this repo.

**`just wire` registers it for you.** The Cardigann definition
(`data/prowlarr/Definitions/Custom/comet-local.yml`, tracked in git) lives in prowlarr's
`Definitions/Custom` and is mounted in with `/config`, so Prowlarr loads it at startup;
`just wire` then creates the
**Comet (Local)** indexer at the internal-only service URL `http://comet:8000` with
**no API key**, and keeps it re-pointed/enabled on later runs. It syncs to Sonarr/Radarr
like any other indexer — no Prowlarr GUI step needed.

The definition queries Comet's **native Torznab API** (`/torznab/api`), so plain-text
searches are resolved by Comet's own metadata (movies via `t=movie`, TV via `t=tvsearch`
with `season`/`ep`); `{imdbid:tt123456}` still gives the most precise hits — there is no
fake-IMDb fallback anymore. Empty-query `t=search` requests (how Sonarr/Radarr validate a
synced indexer and poll RSS) are answered with Comet's **recent** feed (`t=search&cat=…`),
which is what keeps **Comet (Local)** syncing into the Arr apps.

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
  (Debridio, TorBox, AIOStreams) are wired as env placeholders — fill the keys in
  `stacks/media-server/.env` and enable their `SCRAPE_*` toggles (see `.env.example`).
  AIOStreams' URL is given a non-empty placeholder default because Comet crashes at
  import if it ever sees an empty `AIOSTREAMS_URL`; set the real URL to use it.
- The `Comet (Local)` indexer needs no debrid account and returns cached/debrid-ready releases.
  Its results are marked `[DEBRID-CACHED]` and receive a preference score in the shipped Direct
  Play profiles, while non-Comet results remain eligible for uncached downloads.
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
