---
title: Indexers
parent: Services
nav_order: 11
---

# Indexers: Prowlarr, self-hosted Comet, and AltHub

Prowlarr is the single place indexers are configured; everything syncs to Sonarr/Radarr via
"Apps" (wired in [Prowlarr](prowlarr)). Any time after the stack is up
([Quickstart §9](../quickstart#9-set-up-the-apps)) — but you need at least one before grabs
work.

## Recommended indexers

| Indexer      | Type               | Cost               | Where it fits                           |
| ------------ | ------------------ | ------------------ | --------------------------------------- |
| Comet (Local) | torrent aggregator | free (self-hosted) | debrid-cached streams through Decypharr |
| AltHub       | Usenet             | $20 lifetime       | Usenet streaming through TorBox         |

Detailed provider recommendations live in [Providers](../providers).

## Self-hosted Comet

The self-hosted **Comet (Local)** indexer is documented separately in [Comet](comet), including
its DMM ingestion, native Torznab API, Prowlarr adapter, scraper settings, and troubleshooting.

## Adding a regular Usenet indexer (e.g. AltHub)

1. Buy / register (see [Providers](../providers)), then take the **API key + Newznab URL** from the
   indexer's profile page.
2. Prowlarr → Indexers → **+** → **Newznab**: paste the URL and API key, enable, test, save.
3. It syncs to Sonarr/Radarr automatically via the Apps configured earlier. With TorBox Pro and
   Decypharr, the resulting Usenet media is streamed through the debrid mount.
