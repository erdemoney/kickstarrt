---
title: Prowlarr
parent: Services
nav_order: 7
---

# Prowlarr: indexer management

Prowlarr is the single place to configure Usenet indexers. Its Apps connections push those
indexers to Radarr and Sonarr.

## Setup

Open `https://prowlarr.<DOMAIN>` over the tailnet and create the administrator account. Add a
Usenet indexer under **Indexers → + → Newznab**, using the URL and API key from the indexer's
profile; test and save it. Prowlarr syncs it to Sonarr and Radarr through the app connections
managed by `just wire`. Assign the `tv` or `movies` category and quality profile under the
indexer's **Mappings** tab so results use the categories InfiniDysk accepts. Torrent indexers are
not useful here because this stack has no torrent client.

See [Providers](../providers) for recommended Usenet subscriptions. Add only indexers compatible
with the stack's Usenet workflow.

`just wire` creates the Radarr and Sonarr application connections. Do not recreate those
application connections manually unless you have intentionally changed them.

## Internal connections

Prowlarr reaches the other containers over the `internal` network:

```text
http://radarr:7878
http://sonarr:8989
```

Use service names for application URLs, never public hostnames or `localhost`. See [Service
wiring](wiring) for the shared networking model and the
[Prowlarr quick-start guide](https://wiki.servarr.com/prowlarr/quick-start-guide) for product
documentation.
