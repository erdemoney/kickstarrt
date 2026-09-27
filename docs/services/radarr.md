---
title: Radarr
parent: Services
nav_order: 5
---

# Radarr: movie management

Radarr manages movies, sends searches to the indexers configured in Prowlarr, and imports the
finished releases InfiniDysk downloads into `/mnt/usenet/library/movies`. `just wire` configures
its root folder, InfiniDysk download client, and connections used by Prowlarr and Seerr.

## Initial setup

Open `https://radarr.<DOMAIN>` over the tailnet and create the administrator account. The API key
is under **Settings → General → Security**. If it changes, run `just wire` again.

The movie root folder is:

```text
/mnt/usenet/library/movies
```

That is a plain directory on the shared bind, created by `just prepare` and writable by the
container's user. See [Service wiring](wiring#root-folders) for the path model.

## Quality profile

Select the shipped **Direct Play** profile. Recyclarr creates and maintains it automatically from
`data/recyclarr/configs/radarr.yml`. The profile favors Remux and WEB releases, allows HEVC 4K,
and rejects formats likely to force Jellyfin into a video
transcode. See [Recyclarr](recyclarr) for the scoring rationale and tuning workflow.

## Seerr integration

Seerr uses `http://radarr:7878`, the Radarr API key, `/mnt/usenet/library/movies`, and **Direct
Play**. `just wire` reconciles these fields; public hostnames are for browser access only.
