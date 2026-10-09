---
title: Radarr
parent: Services
nav_order: 5
---

# Radarr: movie management

Radarr manages movies, searches through Prowlarr, and imports completed releases from InfiniDysk.

Open `https://radarr.<DOMAIN>` over the tailnet and create the administrator account. `just wire`
configures the root folder (`/mnt/usenet/library/movies`), InfiniDysk download client, and app
connections. If you regenerate the API key, run `just wire` again.

## Quality profile

Select the shipped **Direct Play** profile. Recyclarr creates and maintains it automatically from
`data/recyclarr/configs/radarr.yml`. The profile favors Remux and WEB releases, allows HEVC 4K,
rejects HD x265 and formats likely to force Jellyfin into a video transcode, and caps releases at
375 MB/min to accommodate slower streaming connections. Recyclarr also applies the TRaSH movie
naming format with Jellyfin-compatible TMDb IDs. `just wire` sets the profile language to **Original**
as recommended by [TRaSH](https://trash-guides.info/Radarr/radarr-setup-quality-profiles/).
Recyclarr sets **Download Propers and Repacks** to **Do Not Prefer**, allowing the profile's
Repack/Proper custom-format scores to decide. See [Recyclarr](recyclarr) for the scoring rationale
and tuning workflow.

`just wire` enables **Settings → Media Management → File Management → Skip Free Space Check**.
InfiniDysk imports `.strm` links instead of storing each release's full payload on the library
volume, so comparing the release's advertised size to local free space would reject large releases.

## Manage Radarr and Sonarr from iPhone

[Ruddarr](https://ruddarr.com) is a free, open-source iOS companion app for administering Radarr
and Sonarr. It lets you browse the library and calendar, start searches, and manage the queue or
history; it does not run on the server.

Connect your iPhone to the tailnet, then configure each app in Ruddarr with its **Application
URL**: `https://radarr.<DOMAIN>` and `https://sonarr.<DOMAIN>`. These admin panels are tailnet-only;
do not publish them just to use Ruddarr. See [Tailscale](../tailscale) for private access.

## Further reading

- [Radarr documentation](https://wiki.servarr.com/radarr)
