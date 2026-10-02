---
title: Services
nav_order: 7
has_children: true
---

# Services

Stack-specific configuration, integration notes, and troubleshooting for the media apps and edge
services. For general application usage, each page points to the official documentation.

## Service map

| Service | Role |
| --- | --- |
| [Jellyfin](services/jellyfin) | Playback and library management |
| [Seerr](services/seerr) | User requests |
| [Maintainerr](services/maintainerr) | Rule-based library cleanup |
| [InfiniDysk](services/infinidysk) | Usenet download gateway and `.strm` streaming |
| [Radarr](services/radarr) | Movie management |
| [Sonarr](services/sonarr) | Series management |
| [Prowlarr](services/prowlarr) | Indexer management and application sync |
| [Recyclarr](services/recyclarr) | Quality profile synchronization |
| [Bazarr](services/bazarr) | Subtitle management |

## Edge services

| Service | Role |
| --- | --- |
| [Traefik](services/traefik) | HTTPS routing, certificates, and service exposure |
| [CrowdSec](services/crowdsec) | Edge detection and blocking |
| [CoreDNS](services/coredns) | Tailnet split-DNS resolver |

The Usenet provider and recommended indexers are covered in [Providers](providers); add indexers
through [Prowlarr](services/prowlarr).
