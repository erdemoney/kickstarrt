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
connections. Configure provider credentials and language profiles in Bazarr; assign a profile to
the relevant libraries and choose whether subtitles are stored alongside media. Those choices are
user-specific, so `just wire` leaves them untouched.

See the [Bazarr wiki](https://wiki.bazarr.media/) for provider and language-profile guidance.
For provider recommendations, see [Providers → Subtitle providers](../providers#subtitle-providers).
