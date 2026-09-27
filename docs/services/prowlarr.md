---
title: Prowlarr
parent: Services
nav_order: 7
---

# Prowlarr: indexer management

Prowlarr is the single place to configure Usenet indexers. Its Apps connections push those
indexers to Radarr and Sonarr.

## Setup

Open `https://prowlarr.<DOMAIN>` over the tailnet and create the administrator account. Add
indexers under **Indexers**, then test and save them. Usenet indexers are added as **Newznab** with
the URL and API key from your indexer ([Indexers](indexers)); torrent indexers have nothing to
download through on a Usenet stack and should be left out.

`just wire` creates the Radarr and Sonarr application connections. Do not recreate those
application connections manually unless you have intentionally changed them.

## Internal connections

Prowlarr reaches the other containers over the `internal` network:

```text
http://radarr:7878
http://sonarr:8989
```

Use service names for application URLs, never public hostnames or `localhost`. See [Service
wiring](wiring) for the shared networking model and [Indexers](indexers) for the end-to-end
workflow.
