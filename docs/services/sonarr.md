---
title: Sonarr
parent: Services
nav_order: 6
---

# Sonarr: series management

Sonarr manages series, sends searches to the indexers configured in Prowlarr, and imports the
resulting symlinks into `/mnt/shows`. `just wire` configures its root folder, Decypharr download
client, and connections used by Prowlarr and Seerr.

## Initial setup

Open `https://sonarr.<DOMAIN>` over the tailnet and create the administrator account. The API key
is under **Settings → General → Security**. If it changes, run `just wire` again.

The series root folder is:

```text
/mnt/shows
```

Do not use `/mnt/decypharr` as a root folder. It is Decypharr's read-only virtual filesystem;
the shared library directory is the import destination. See [Service wiring](wiring) for the
mount and symlink model.

## Quality profiles

Use **Direct Play** for regular series. For anime, set the series type to **Anime** and select
**Direct Play (Anime)**. Recyclarr creates and maintains both profiles from
`data/recyclarr/configs/sonarr.yml`. See [Recyclarr](recyclarr) for the profile design.

## Seerr integration

Seerr uses `http://sonarr:8989`, the Sonarr API key, `/mnt/shows`, and the selected quality profile.
`just wire` reconciles these fields; public hostnames are for browser access only.
