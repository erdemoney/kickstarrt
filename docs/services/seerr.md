---
title: Seerr
parent: Services
nav_order: 2
---

# Seerr: media requests

Seerr is the user-facing request portal. It uses Jellyfin for authentication and availability,
then sends approved requests to Radarr or Sonarr.

## Stack setup

Open `https://seerr.<DOMAIN>` over the tailnet. `just wire` can complete Seerr's first-run setup
through Jellyfin login. Create Jellyfin libraries first so they are available for requests.

Seerr's configuration is stored under `data/seerr/config`. The panel is tailnet-only by default;
to publish it, run `just public enable seerr`, then follow [Traefik's public access steps](traefik#public-access).

For request management and user-facing settings, see the
[Seerr documentation](https://docs.seerr.dev/).
