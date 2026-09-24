---
title: Indexers
parent: Services
nav_order: 11
---

# Indexers: Prowlarr, hosted Zilean, and AltHub

Prowlarr is the single place indexers are configured; everything syncs to Sonarr/Radarr via
"Apps" (wired in [Prowlarr](prowlarr)). Any time after the stack is up
([Quickstart §9](../quickstart#9-set-up-the-apps)) — but you need at least one before grabs
work.

## Recommended indexers

| Indexer      | Type                     | Cost               | Where it fits                           |
| ------------ | ------------------------ | ------------------ | --------------------------------------- |
| Zilean       | torrent (DMM hashlist)   | free (hosted)      | debrid-cached streams through Decypharr |
| AltHub       | Usenet                   | $20 lifetime       | Usenet streaming through TorBox         |

Detailed provider recommendations live in [Providers](../providers).

## Hosted Zilean

The hosted **Zilean (DMM)** indexer is documented separately in [Zilean](zilean), including the
Prowlarr adapter and cache-verification notes.

## Adding a regular Usenet indexer (e.g. AltHub)

1. Buy / register (see [Providers](../providers)), then take the **API key + Newznab URL** from the
   indexer's profile page.
2. Prowlarr → Indexers → **+** → **Newznab**: paste the URL and API key, enable, test, save.
3. It syncs to Sonarr/Radarr automatically via the Apps configured earlier. With TorBox Pro and
   Decypharr, the resulting Usenet media is streamed through the debrid mount.
