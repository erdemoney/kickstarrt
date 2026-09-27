---
title: Sonarr
parent: Services
nav_order: 6
---

# Sonarr: series management

Sonarr manages series, sends searches to the indexers configured in Prowlarr, and imports the
finished releases InfiniDysk downloads into `/mnt/usenet/library/shows`. `just wire` configures
its root folder, InfiniDysk download client, and connections used by Prowlarr and Seerr.

## Initial setup

Open `https://sonarr.<DOMAIN>` over the tailnet and create the administrator account. The API key
is under **Settings → General → Security**. If it changes, run `just wire` again.

The series root folder is:

```text
/mnt/usenet/library/shows
```

That is a plain directory on the shared bind, created by `just prepare` and writable by the
container's user. See [Service wiring](wiring#root-folders) for the path model.

## Quality profiles

Use **Direct Play** for regular series. For anime, set the series type to **Anime** and select
**Direct Play (Anime)**. Recyclarr creates and maintains both profiles from
`data/recyclarr/configs/sonarr.yml`. See [Recyclarr](recyclarr) for the profile design.

## Seerr integration

Seerr uses `http://sonarr:8989`, the Sonarr API key, `/mnt/usenet/library/shows`, and the selected
quality profile. `just wire` reconciles these fields; public hostnames are for browser access only.
