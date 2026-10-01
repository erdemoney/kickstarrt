---
title: Jellyfin
parent: Services
nav_order: 1
---

# Jellyfin: playback setup

On a fresh install, `just wire` completes Jellyfin's first-run wizard and creates a `Kickstarrt` API
key. It also configures Sonarr and Radarr to trigger a library scan after imports. See
[Service wiring](wiring#automated-wiring).

## Libraries

Add these folders as Movies and Shows libraries:

```text
/mnt/usenet/library/movies
/mnt/usenet/library/shows
```

The shared bind is mounted at the same path in Jellyfin and the *arrs, so no path mapping is
needed ([Service wiring](wiring#root-folders)). Do not add `/mnt/usenet/completed-downloads`;
that is InfiniDysk's staging area, not library content. For TV series whose episode order differs
between Jellyfin and Sonarr, choose matching metadata providers or identify the series using its
TVDB entry.

## CPU-only playback

The VPS has no GPU, so set Jellyfin's **Transcoding path** to `/transcode` (a tmpfs) and disable
video transcoding for each user. Keep conversion without video re-encoding (remux) and audio
transcoding enabled. Unsupported video formats then fail rather than consuming CPU on a software
transcode. The shipped **Direct Play** profiles in [Recyclarr](recyclarr) favor formats that work
with this policy. See the [Jellyfin playback documentation](https://jellyfin.org/docs/general/clients/codec-support/)
for playback and transcoding settings.

## Troubleshooting

If a library is empty or an import is missing, confirm the library path above, run **Scan All
Libraries**, then check that the files are visible in the container:

```bash
docker exec jellyfin ls -la /mnt/usenet/library/shows /mnt/usenet/library/movies
```

If an imported `.strm` file will not play, inspect its URL and test that URL from inside the
Jellyfin container (`docker exec jellyfin curl -fsSI <url>`). It must resolve to InfiniDysk; see
[InfiniDysk troubleshooting](infinidysk#troubleshooting).
