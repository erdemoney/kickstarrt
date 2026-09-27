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
| [InfiniDysk](services/infinidysk) | Usenet download gateway and `.strm` streaming |
| [Radarr](services/radarr) | Movie management |
| [Sonarr](services/sonarr) | Series management |
| [Prowlarr](services/prowlarr) | Indexer management and application sync |
| [Recyclarr](services/recyclarr) | Quality profile synchronization |
| [Bazarr](services/bazarr) | Subtitle management |
| [Back-catalog hunting](services/hunt) | Scheduled missing and quality-upgrade searches |
| [Indexers](services/indexers) | Indexer workflow and provider choices |

The Usenet provider and indexer subscriptions live in the top-level [Providers](providers) page.
