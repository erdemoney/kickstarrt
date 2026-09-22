---
title: Radarr
parent: Services
nav_order: 5
---

# Radarr: movie management

Radarr manages movies, sends searches to the indexers configured in Prowlarr, and imports the
resulting symlinks into `/mnt/movies`. `just wire` configures its root folder, Decypharr download
client, and connections used by Prowlarr and Seerr.

## Initial setup

Open `https://radarr.<DOMAIN>` over the tailnet and create the administrator account. The API key
is under **Settings → General → Security**. If it changes, run `just wire` again.

The movie root folder is:

```text
/mnt/movies
```

Do not use `/mnt/decypharr` as a root folder. It is Decypharr's read-only virtual filesystem;
the shared library directory is the import destination. See [Service wiring](wiring) for the
mount and symlink model.

## Quality profile

Select the shipped **Direct Play** profile. Recyclarr creates and maintains it automatically from
`data/recyclarr/configs/radarr.yml`. The profile favors Remux and WEB releases, allows HEVC 4K,
prefers Comet's debrid-cached results, and rejects formats likely to force Jellyfin into a video
transcode. See [Recyclarr](recyclarr) for the scoring rationale and tuning workflow.

## Seerr integration

Seerr uses `http://radarr:7878`, the Radarr API key, `/mnt/movies`, and **Direct Play**. `just wire`
reconciles these fields; public hostnames are for browser access only.
