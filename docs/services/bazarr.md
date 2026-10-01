---
title: Bazarr
parent: Services
nav_order: 10
---

# Bazarr: subtitles

Bazarr fetches subtitles for media managed by Sonarr and Radarr. `just wire` configures its
connections to both applications while preserving the rest of Bazarr's settings.

## Stack setup

Open `https://bazarr.<DOMAIN>` over the tailnet. Run `just wire` to configure its Sonarr and Radarr
connections. In Bazarr, configure provider credentials under **Settings → Providers**. Under
**Settings → Languages**, enable the languages you want, open **Profiles**, choose **Add New
Profile**, name it, add a language, and save. Set the series and movie default profiles for new
content under **Default Settings**. For existing content, use **Mass Edit** in the Series and
Movies lists to apply the profile. Under **Settings → Sonarr** and **Settings → Radarr**, enable
**Download Only Monitored** to limit automatic downloads to monitored shows, episodes, and movies;
monitor the desired content in Sonarr/Radarr. `just wire` leaves these user-specific choices
untouched.

Set subtitle storage to **Alongside Media File** if you want subtitles beside the `.strm` library
entries. These settings and labels can change between Bazarr versions.

For provider recommendations, see [Providers → Subtitle providers](../providers#subtitle-providers).

## Further reading

- [Bazarr setup guide](https://wiki.bazarr.media/Getting-Started/Setup-Guide/)
