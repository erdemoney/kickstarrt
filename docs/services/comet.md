---
title: Comet
parent: Services
nav_order: 8
---

# Comet: self-hosted debrid indexer

Comet is the stack's self-hosted torrent/debrid indexer. It combines public DMM hashlist
ingestion with scraper results and exposes them to Prowlarr through its native Torznab API.
Results marked `[DEBRID-CACHED]` are preferred by the shipped Radarr and Sonarr profiles.

## Access and wiring

Comet is tailnet-only at `https://comet.<DOMAIN>/admin`. Its internal indexer URL is
`http://comet:8000`; it needs no API key. `just wire` creates the **Comet (Local)** custom indexer
in Prowlarr and keeps it enabled on later runs.

Prowlarr's custom Cardigann adapter for that API is tracked at
`data/prowlarr/Definitions/Custom/comet-local.yml` and mounted into Prowlarr at startup.

## Ingestion

The first DMM ingestion can use sustained CPU for 10–30 minutes and results are not available
until an ingestion cycle completes. It is resumable after interruption; later daily cycles are
incremental. Check progress with:

```bash
just logs-svc comet
```

Nyaa, AnimeTosho, and SeaDex are enabled by default for anime. Peerflix is also enabled for both
live searches and background pre-caching; Comet deduplicates results in its cache. Override
`SCRAPE_SEADEX`, `SEADEX_ANIME_ONLY`, or `SCRAPE_PEERFLIX` in `stacks/media-server/.env` if needed.
TorrentsDB remains disabled by default because it overlaps with the other aggregator scrapers.
Credentialed scrapers are also controlled by the `SCRAPE_*` settings in that file.

See [Indexers](indexers) for adding other indexers and [Recyclarr](recyclarr) for how cached Comet
results affect selection.
