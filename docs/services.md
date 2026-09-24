---
title: Services
nav_order: 5
has_children: true
---

# Services

Service-specific setup and operations for the media stack. Start with
[Service wiring](services/wiring) for the shared Docker network, paths, API keys, and automated
integration behavior.

## Service map

| Service | Role |
| --- | --- |
| [Jellyfin](services/jellyfin) | Playback and library management |
| [Seerr](services/seerr) | User requests |
| [Decypharr](services/decypharr) | Debrid filesystem and download gateway |
| [Radarr](services/radarr) | Movie management |
| [Sonarr](services/sonarr) | Series management |
| [Prowlarr](services/prowlarr) | Indexer management and application sync |
| [Zilean](services/zilean) | Debrid-packed DMM release indexer |
| [Recyclarr](services/recyclarr) | Quality profile synchronization |
| [Bazarr](services/bazarr) | Subtitle management |
| [Back-catalog hunting](services/hunt) | Scheduled missing and quality-upgrade searches |
| [Indexers](services/indexers) | Indexer workflow and provider choices |

Provider subscriptions and pricing remain in the top-level [Providers](providers) page.
