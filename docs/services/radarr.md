---
title: Radarr
parent: Services
nav_order: 5
---

# Radarr: movie management

Radarr manages movies, searches through Prowlarr, and imports completed releases from InfiniDysk.

Open `https://radarr.<DOMAIN>` over the tailnet and create the administrator account. `just wire`
configures the root folder (`/mnt/usenet/library/movies`), InfiniDysk download client, and app
connections. If you regenerate the API key, run `just wire` again. The shared path model is in
[Service wiring](wiring#root-folders).

## Quality profile

Select the shipped **Direct Play** profile. Recyclarr creates and maintains it automatically from
`data/recyclarr/configs/radarr.yml`. The profile favors Remux and WEB releases, allows HEVC 4K,
and rejects formats likely to force Jellyfin into a video
transcode. See [Recyclarr](recyclarr) for the scoring rationale and tuning workflow.

For movie management and search settings, see the [Radarr documentation](https://wiki.servarr.com/radarr).
