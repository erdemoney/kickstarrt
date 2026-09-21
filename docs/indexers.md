---
title: Indexers
nav_order: 10
---

# Indexers: Prowlarr, custom Cardigann, and AltHub

Prowlarr is the single place indexers are configured; everything syncs to Sonarr/Radarr via
"Apps" (wired in [The \*arrs](arrs)). Any time after the stack is up
([Quickstart §9](quickstart#9-set-up-the-apps)) — but you need at least one before grabs
work.

## Recommended indexers

| Indexer                      | Type               | Cost               | Where it fits                           |
| ---------------------------- | ------------------ | ------------------ | --------------------------------------- |
| Torrentio (custom Cardigann) | torrent aggregator | needs a debrid key | debrid-cached streams through Decypharr |
| AltHub                       | Usenet             | $20 lifetime       | Usenet streaming through TorBox         |

Detailed recommendations live in [Services](services).

## Custom indexers (Torrentio, comet, …)

Prowlarr can run **custom Cardigann indexers**: YAML definitions that talk to a torrent
aggregator / search API (Torrentio, comet, zilean, knightcrawler, ...), so results
flow through the normal Prowlarr → Sonarr/Radarr sync and grabs go to Decypharr for debrid
streaming.

1. Install **all** bundled definitions with one command (run on the server; it downloads the
   Prowlarr-Indexers repo archive, copies its `Custom/` dir into prowlarr's config dir, and
   restarts prowlarr):

   ```bash
   just add-indexers
   ```

   (The manual step it automates: put every `*.yml` from
   `https://github.com/dreulavelle/Prowlarr-Indexers/tree/main/Custom` into
   `data/prowlarr/Definitions/Custom` and recreate prowlarr.) Definitions are **inert
   until you add them in Prowlarr**, so installing the whole set saves a pick-a-name step.

   Currently shipped (all are `Custom/<name>.yml` from that repo):

   | Name          | What it is                                      | Needs                        |
   | ------------- | ----------------------------------------------- | ---------------------------- |
   | torrentio     | Torrentio aggregator (ezTV, 1337x, TPB, …)      | debrid provider key          |
   | comet         | Comet search API                                | service URL + key            |
   | aiostreams    | AioStreams search                               | service URL + key            |
   | aiostreams-api| AioStreams API search                           | API key                      |
   | annatar       | Annatar search API                              | service URL + key            |
   | debridio      | Debrid.io search                                | API key                      |
   | elfhosted-public | ElfHosted public search                      | service URL                  |
   | elfhosted-internal | ElfHosted internal search                   | service URL                  |
   | elfhosted-torrentio | ElfHosted Torrentio-compatible search     | service URL                  |
   | knightcrawler | KnightCrawler search                            | service URL + key            |
   | orionoid      | Orionoid search                                 | Orionoid API key (paid)      |
   | stremthru     | StremThru aggregator                            | service URL                  |
   | torrentclaw   | TorrentClaw search                              | service URL + key            |

   A missing name is not a bug — the repo just added or renamed it; re-run
   `just add-indexers` to pick up any changes.

   The `comet` and `torrentio` definitions here target *external* instances. The stack's own
   self-hosted Comet is registered as **Comet (Local)** by `just wire`, not by `add-indexers`
   (see below).

2. Prowlarr → **Indexers** → `+` → search the name (e.g. **Torrentio**)
   → add it.
   - Fill in whatever the definition asks for (see the "Needs" column above) — e.g. Torrentio
     wants your **Real-Debrid (or supported-debrid) API key**.
   - Torrentio example: `default_opts` holds the provider list plus `qualityfilter=scr,cam`;
     tweak the providers or sort if you want.
   - Save, enable, and confirm a green test; enable for movies/TV in the Sync Profile.
3. It syncs to Sonarr/Radarr like any indexer. For precise hits in Prowlarr search use
   `{imdbid:tt123456}` / `{imdbid:tt1234567}{season:00}{episode:00}`.

### Self-hosted Comet

The media stack runs **Comet** (`stacks/media-server/compose.yaml`) — a torrent/debrid
search add-on whose **DMM ingester** imports the public DMM hashlists into its own Postgres
database. It is exposed only on the tailnet:
no public router, no published ports. Its admin dashboard (DMM ingestion progress,
scraper health, cache stats) lives at `https://comet.<DOMAIN>` (password set by
`just init`).

**`just wire` registers it for you.** The Cardigann definition
(`stacks/media-server/prowlarr/comet-local.yml`) is bind-mounted read-only into prowlarr's
`Definitions/Custom`, so Prowlarr loads it at startup; `just wire` then creates the
**Comet (Local)** indexer at the internal-only service URL `http://comet:8000` with
**no API key**, and keeps it re-pointed/enabled on later runs. It syncs to Sonarr/Radarr
like any other indexer — no Prowlarr GUI step needed.

The definition queries Comet's **native Torznab API** (`/torznab/api`), so plain-text
searches are resolved by Comet's own metadata (movies via `t=movie`, TV via `t=tvsearch`
with `season`/`ep`); `{imdbid:tt123456}` still gives the most precise hits — there is no
fake-IMDb fallback anymore.

Notes:
- **First DMM ingestion is the heavy one**: ~10–30 min of sustained CPU (more on a 2 vCPU box)
  as Comet downloads and indexes the shared hashlists; results are only served after at least
  one ingestion cycle (watch `just logs-svc comet`). Ingestion is **resumable** — if it's
  interrupted (reboot, OOM), the next start picks up where it left off. Later cycles
  (`DMM_INGEST_INTERVAL`, daily) are incremental and light.
- Comet also scrapes the public **MediaFusion** (`mediafusion.elfhosted.com`) and
  **StremThru** (`stremthru.13377001.xyz`) instances, and runs a modest **background
  pre-cacher** (single worker, capped runs). Torrentio is intentionally left off:
  `torrentio.strem.fun` Cloudflare-challenges VPS/datacenter IPs. Credentialed scrapers
  (Debridio, TorBox, AIOStreams) are wired as env placeholders — fill the keys in
  `stacks/media-server/.env` and enable their `SCRAPE_*` toggles (see `.env.example`).
- The `Comet (Local)` indexer needs no debrid account and returns cached/debrid-ready releases;
  pair it with Torrentio or a provider indexer rather than running it alone. Its results are
  marked `[DEBRID-CACHED]` and receive a preference score in the shipped Direct Play profiles,
  while non-Comet results remain eligible for uncached downloads.
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
