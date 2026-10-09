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

The stack is designed for a CPU-only VPS and remote Usenet streaming. **Direct Play** therefore
optimizes for files clients can play without video re-encoding:

- The quality ladder favors Remux, WEB, and Blu-ray releases at 2160p and 1080p. Radarr scores
  Remux, WEB, and HD/UHD Blu-ray release-group tiers; Sonarr scores the tiers configured for its
  regular and anime profiles.
- Quality definitions keep TRaSH's minimum sizes but cap files at **375 MB/min** (about
  **50 Mbps average**), with the preferred size just below that ceiling. This intentional,
  per-quality file-size limit is shared by all profiles in each Arr instance to accommodate slower
  streaming connections; it does not cap instantaneous bitrate or re-encode media.
- Radarr keeps 4K HEVC eligible while rejecting 720p/1080p x265; UHD releases commonly use HEVC.
  Sonarr keeps HEVC eligible, with the anime-specific Hi10 title rule described below.
- Audio is not penalized because audio transcoding is comparatively inexpensive.
- Radarr and Sonarr use TRaSH naming formats with quality/release metadata in filenames and
  Jellyfin-compatible TMDb/TVDb IDs in movie/series folders.
- Availability is not asserted at the indexer; InfiniDysk verifies the release against your
  Usenet provider at grab time, and repairs it in the background afterwards
  ([InfiniDysk](infinidysk)).
- Disk images, Dolby Vision without an HDR10 fallback, generated dynamic HDR, 3D, upscaled releases,
  extras, sing-along versions, AV1, VP9, VC-1, MPEG-2, HD x265, low-quality, and obfuscated releases
  receive `-10000` and are never grabbed.
- Both Recyclarr configs set **Do Not Prefer** for Propers and Repacks; the Repack/Proper custom
  formats (+5/+6/+7) supply those preferences. `just wire` sets Radarr's language to **Original**
  per [TRaSH's Radarr guide](https://trash-guides.info/Radarr/radarr-setup-quality-profiles/), since
  Recyclarr does not manage language on this manual profile.

The `0` minimum format score means normal releases remain eligible; the `-10000` scores are the
hard exclusions.

### Completion first, then 4K

The quality ladders are completion-first: they run all the way down to **SDTV** (Sonarr) /
**DVD-R** (Radarr), so a monitored missing episode or movie is *always* grabbable instead of
staying empty while waiting for a 4K release. Once a low-tier landing fills the gap, subsequent
searches upgrade it toward the profile ceiling for free over Usenet. The `until_quality` ceilings
are untouched, so 4K is still chased - just never allowed to leave a gap behind.

Sonarr's season packs carry a large preference bonus (`+5000`) so a grabbable pack always beats
scattered individual-episode grabs. Note this cannot override Sonarr's built-in all-or-nothing pack
rule - a pack is only grabbed when it upgrades *every* episode or the whole season is missing -
so partially-filled mixed-quality seasons still fill episode-by-episode.

## Anime profile

Sonarr also receives **Direct Play (Anime)**. It uses the TRaSH anime recipe but is adapted to the
same playback policy:

- Blu-ray remux and Blu-ray 1080p are one quality tier and form the ceiling.
- Anime WEB releases that identify as HDTV are folded into the WEB tiers.
- SeaDex anime BD/Web release-group tiers determine preference.
- Anime releases tagged `Hi10`/`Hi10P` are rejected to avoid H.264 High 10 transcodes. The rule
  matches those release-title tags; ordinary H.264 and HEVC (including 10-bit HEVC) remain eligible.
- Raw, low-quality, dubs-only, and French-only releases are rejected for this household.

Set the Sonarr series type to **Anime** and choose this profile for anime. Regular series should
use **Direct Play**.

## Tuning and synchronization

Edit the YAML under `data/recyclarr/configs/` when changing scores, quality tiers, or exclusions.
Local custom formats live under `data/recyclarr/custom-formats/` and are registered in
`data/recyclarr/settings.yml`. The comments in the config files explain the corresponding TRaSH IDs
and local rules. Recyclarr syncs the naming settings but does not bulk-rename files already in the
library; use the Arr rename-files action if you want existing files to adopt the new format. Force a
sync after editing:

```bash
docker compose -f stacks/media-server/compose.yaml exec recyclarr recyclarr sync
```

If a profile is missing or an Arr API key was regenerated, run `just wire`, then inspect:

```bash
docker logs recyclarr
```

## Further reading

- [Official Recyclarr documentation](https://recyclarr.dev/wiki/)
