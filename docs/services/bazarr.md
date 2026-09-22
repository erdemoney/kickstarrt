---
title: Bazarr
parent: Services
nav_order: 10
---

# Bazarr: subtitles

Bazarr fetches subtitles for media managed by Sonarr and Radarr. `just wire` configures its
connections to both applications while preserving the rest of Bazarr's settings.

## Setup

Open `https://bazarr.<DOMAIN>` over the tailnet. Configure subtitle providers under **Settings →
Providers**. OpenSubtitles.com is the primary provider; subdl.com is a useful free fallback.

Create a language profile under **Languages**, assign it to the relevant Sonarr/Radarr libraries,
and set the subtitle folder to **Alongside media file**. Bazarr only fetches subtitles for titles
added after a language profile is assigned.

OpenSubtitles.com is the primary provider; its free tier is rate-limited. `subdl.com` is a useful
fallback. Whisper is an optional AI-generated fallback that requires a separate ASR service.
Rank providers by preference and raise a language's minimum score if results are out of sync or
machine-translated.

Use `http://sonarr:8989` and `http://radarr:7878` for the application connections. The services
share the `internal` Docker network; public hostnames are for browser access only.
