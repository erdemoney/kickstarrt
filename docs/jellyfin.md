---
title: Jellyfin
nav_order: 7
---

# Jellyfin: playback setup

The admin account is created on Jellyfin's **first login** (the setup wizard) — or, on a fresh
install, by `just wire`, which completes the wizard through its API and mints a `Kickstarrt` API key
([*arrs → Automated wiring](arrs#automated-wiring)). From there
the two things that need configuring are the libraries — they point at the library dirs on the
shared bind (`/mnt/shows`, `/mnt/movies`) — and the transcode policy, tuned for a CPU-only VPS.

> **Scanning is automatic.** `just wire` configures Sonarr/Radarr to push a library scan to
> Jellyfin whenever media is imported, upgraded, or renamed (the *arr → Jellyfin connections,
> library update on). Jellyfin's own filesystem watcher is deliberately not relied on: imports
> arrive as symlink renames on the debrid FUSE mount, which do not always trigger it. You can
> still run **Scan All Libraries** manually at any time.

## 1. Libraries

No path mapping needed: the compose already binds the whole shared tree into Jellyfin at `/mnt`
(`- /mnt/debrid:/mnt:rslave`), so the library dirs (`/mnt/shows`, `/mnt/movies`), Decypharr's
DFS mount (`/mnt/decypharr`), and the symlinks Decypharr hands over all resolve at the same
places as in the \*arrs ([Decypharr](decypharr#visibility-of-the-mount)).

Dashboard → **Libraries** → **Add Media Library**:

- **Content type** — Movies / Shows (or whatever your folder holds).
- **Folders** → **+** → add the library folder on the shared bind, e.g. `/mnt/shows` or
  `/mnt/movies`.
- Save, then **Scan All Libraries**.

If a library shows empty here but populated on the host, it's the classic mount-propagation
mistake ([Decypharr → Visibility of the mount](decypharr#visibility-of-the-mount)).

Also set Dashboard → **Playback** → **Transcoding path** to `/transcodes` — a tmpfs, so
transcode scratch never touches disk. This stack transcodes in software (no GPU,
[FAQ](faq#why-does-jellyfin-transcode-in-software-no-gpu)) and Recyclarr ships a **Direct
Play** quality profile, so the goal is to keep playback direct and never let a client push
the server into a CPU-only video transcode. The profile permits 4K/HEVC (every UHD release is
HEVC), so on clients without HEVC support the per-user policy below is what keeps the CPU idle:
remux plays, video re-encoding fails cleanly instead of transcode-spiking.

## 2. Transcode policy: no video transcoding, remux + audio transcoding stay on

Jellyfin has **no global "disable video transcoding" switch** — it's set per user
([upstream#645](https://github.com/jellyfin/jellyfin/issues/645)). Open
**Dashboard → Users → edit the user → Access** → the *Media playback* block:

| Setting                                                | Value | Meaning                                                  |
| ------------------------------------------------------ | ----- | -------------------------------------------------------- |
| Allow media playback                                   | on    |                                                          |
| Allow **video playback that requires transcoding**     | **off** | never re-encode video (software transcode = CPU churn) |
| Allow **video playback that requires conversion without re-encoding** | **on** | remux / direct stream — container change, streams copied |
| Allow **audio playback that requires transcoding**     | **on** | audio transcode is cheap and often needed                |

Repeat for **each user** — a new user inherits the defaults (video transcoding on), so set
it when you add one.

What this buys you: anything that only needs a container remux or an audio transcode plays;
anything that *requires* video transcoding (codec the client can't play, or burned-in
subtitles) fails with an error instead of transcode-spiking the server — by design. Keep
clients direct-play friendly (bitrate caps live on the client, not the server) and the VPS
stays idle.
