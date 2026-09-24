---
title: Recyclarr
parent: Services
nav_order: 9
---

# Recyclarr: quality profiles

Recyclarr synchronizes the tracked quality profiles into Radarr and Sonarr. The container reads
`data/recyclarr/configs/radarr.yml` and `sonarr.yml`, creates the profiles on the first run, and
syncs them daily. There is nothing to paste into either Arr UI.

## Why these profiles are custom

The stack is designed for a CPU-only VPS and remote debrid playback. **Direct Play** therefore
optimizes for files clients can play without video re-encoding:

- The quality ladder favors Remux, WEB, and Blu-ray releases at 2160p and 1080p.
- HEVC is allowed, including 4K, because UHD releases are commonly HEVC and direct-play-capable
  clients can handle them.
- Audio is not penalized because audio transcoding is comparatively inexpensive.
- Debrid-cache state is not asserted at the indexer (Zilean mirrors the DMM hashlist without
  per-hash cache checks); Decypharr's `download_uncached=false` gate is the cache verification at
  grab time.
- Disk images, Dolby Vision without an HDR10 fallback, AV1, VP9, VC-1, MPEG-2, low-quality, and
  obfuscated releases receive `-10000` and are never grabbed.

The `0` minimum format score means normal releases remain eligible; the `-10000` scores are the
hard exclusions.

## Anime profile

Sonarr also receives **Direct Play (Anime)**. It uses the TRaSH anime recipe but is adapted to the
same playback policy:

- Blu-ray remux and Blu-ray 1080p are one quality tier and form the ceiling.
- Anime WEB releases that identify as HDTV are folded into the WEB tiers.
- SeaDex anime BD/Web release-group tiers determine preference.
- x265 is not penalized because anime BD encodes are commonly 10-bit HEVC.
- Raw, low-quality, dubs-only, and French-only releases are rejected for this household.

Set the Sonarr series type to **Anime** and choose this profile for anime. Regular series should
use **Direct Play**.

## Tuning and synchronization

Edit the YAML under `data/recyclarr/configs/` when changing scores, quality tiers, or exclusions.
The comments in those files explain the corresponding TRaSH IDs and are the source-adjacent
reference. Force a sync after editing:

```bash
docker compose -f stacks/media-server/compose.yaml exec recyclarr recyclarr sync
```

If a profile is missing or an Arr API key was regenerated, run `just wire`, then inspect:

```bash
docker logs recyclarr
```
