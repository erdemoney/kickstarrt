---
title: Zilean
parent: Services
nav_order: 8
---

# Zilean: debrid-packed DMM indexer

Zilean is an unofficial DMM indexer: it serves the public DMM hashlist (DebridMediaManager's
crowd-sourced cached release list) over a simple search API. The stack uses a hosted instance, so
there is no service to run and no ingestion delay. Results are the exact debrid-cached packs that
the DMM community surfaces.

## Access and wiring

Our custom Cardigann adapter is a fork of the community
[Zilean definition](https://github.com/dreulavelle/Prowlarr-Indexers) with
`https://zileanfortheweebs.midnightignite.me` added to the source list. It is tracked at
`data/prowlarr/Definitions/Custom/zilean.yml` and mounted into Prowlarr at startup, so `just wire`
only has to register the **Zilean** indexer, preconfigured to point at that hosted instance.

## Cache verification

DMM's `[DEBRID-CACHED]` style guarantees are not asserted by Zilean itself (it mirrors the
hashlist), so this stack does not tag or score results by cache state. Actual cache availability is
still decided per-hash by Decypharr (`download_uncached=false`) at download time.

## Troubleshooting

Check the indexer's test in Prowlarr → Indexers, or hit the instance directly:

```bash
curl -s 'https://zileanfortheweebs.midnightignite.me/dmm/filtered?Query=whatever'
```

See [Indexers](indexers) for adding other indexers and [Recyclarr](recyclarr) for how the quality
profiles select between results.
