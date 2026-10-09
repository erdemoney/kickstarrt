---
title: Sonarr
parent: Services
nav_order: 6
---

# Sonarr: series management

Sonarr manages series, searches through Prowlarr, and imports completed releases from InfiniDysk.

Open `https://sonarr.<DOMAIN>` over the tailnet and create the administrator account. `just wire`
configures the root folder (`/mnt/usenet/library/shows`), InfiniDysk download client, and app
connections. If you regenerate the API key, run `just wire` again.

## Quality profiles

Use **Direct Play** for regular series. For anime, set the series type to **Anime** and select
**Direct Play (Anime)**. Recyclarr creates and maintains both profiles and the episode naming
settings from `data/recyclarr/configs/sonarr.yml`. See [Recyclarr](recyclarr) for the profile and
naming design.

Recyclarr sets **Settings → Media Management → File Management → Download Propers and Repacks** to
**Do Not Prefer** in both Sonarr and Radarr. Their profiles use custom formats to score Propers and
Repacks, so those scores decide between otherwise equal quality tiers rather than the built-in
revision preference overriding them.

`just wire` also enables **Settings → Media Management → File Management → Skip Free Space Check**.
InfiniDysk imports `.strm` links instead of storing each release's full payload on the library
volume, so comparing the release's advertised size to local free space would reject large releases.

For mobile administration of Radarr and Sonarr, see [Ruddarr](radarr#manage-radarr-and-sonarr-from-iphone).

## Further reading

- [Sonarr documentation](https://wiki.servarr.com/sonarr)
