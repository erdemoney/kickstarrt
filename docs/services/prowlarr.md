---
title: Prowlarr
parent: Services
nav_order: 7
---

# Prowlarr: indexer management

Prowlarr is the single place to configure torrent and Usenet indexers. Its Apps connections push
those indexers to Radarr and Sonarr.

## Setup

Open `https://prowlarr.<DOMAIN>` over the tailnet and create the administrator account. Add
indexers under **Indexers**, then test and save them. Add regular Usenet indexers with their
Newznab URL and API key.

`just wire` creates the Radarr and Sonarr application connections and registers the built-in
[Comet](comet) indexer. Do not recreate those application connections manually unless you have
intentionally changed them.

## Internal connections

Prowlarr reaches the other containers over the `internal` network:

```text
http://radarr:7878
http://sonarr:8989
http://comet:8000
```

Use service names for application URLs, never public hostnames or `localhost`. See [Service
wiring](wiring) for the shared networking model and [Indexers](indexers) for the end-to-end
workflow.
