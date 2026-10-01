---
title: Sonarr
parent: Services
nav_order: 6
---

# Sonarr: series management

Sonarr manages series, searches through Prowlarr, and imports completed releases from InfiniDysk.

Open `https://sonarr.<DOMAIN>` over the tailnet and create the administrator account. `just wire`
configures the root folder (`/mnt/usenet/library/shows`), InfiniDysk download client, and app
connections. If you regenerate the API key, run `just wire` again. The shared path model is in
[Service wiring](wiring#root-folders).

## Quality profiles

Use **Direct Play** for regular series. For anime, set the series type to **Anime** and select
**Direct Play (Anime)**. Recyclarr creates and maintains both profiles from
`data/recyclarr/configs/sonarr.yml`. See [Recyclarr](recyclarr) for the profile design.

For series management and search settings, see the [Sonarr documentation](https://wiki.servarr.com/sonarr).
