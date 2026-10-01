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

In Dashboard → **Libraries** → **Add Media Library**, create a Movies library and a Shows library.
For each one, choose the matching folder:

```text
/mnt/usenet/library/movies
/mnt/usenet/library/shows
```

Save each library, then scan. The shared bind is mounted at the same path in Jellyfin and the *arrs,
so no path mapping is needed ([Service wiring](wiring#root-folders)). Do not add
`/mnt/usenet/completed-downloads`; that is InfiniDysk's staging area, not library content.

## CPU-only playback

The VPS has no GPU. Set Dashboard → **Playback** → **Transcoding path** to `/transcode` (a tmpfs),
then disable video transcoding for every user: Dashboard → **Users** → edit a user → **Access** →
**Media playback**.

| Playback setting | Value |
| --- | --- |
| Allow video playback that requires transcoding | Off |
| Allow video playback that requires conversion without re-encoding (remux) | On |
| Allow audio playback that requires transcoding | On |

Repeat for each user; new users inherit the default, which allows video transcoding. With this
policy, video that needs re-encoding fails instead of consuming CPU, while remux and audio
transcoding remain available. The shipped **Direct Play** profiles in [Recyclarr](recyclarr) favor
formats compatible with this policy. See the [Jellyfin playback documentation](https://jellyfin.org/docs/general/clients/codec-support/)
for other playback settings.

## Troubleshooting

If a library is empty or an import is missing, confirm the library path above, run **Scan All
Libraries**, then check that the files are visible in the container:

```bash
docker exec jellyfin ls -la /mnt/usenet/library/shows /mnt/usenet/library/movies
```

If an imported `.strm` file will not play, inspect its URL and test that URL from inside the
Jellyfin container (`docker exec jellyfin curl -fsSI <url>`). It must resolve to InfiniDysk; see
[InfiniDysk troubleshooting](infinidysk#troubleshooting).
