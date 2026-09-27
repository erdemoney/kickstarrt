---
title: Jellyfin
parent: Services
nav_order: 1
---

# Jellyfin: playback setup

The admin account is created on Jellyfin's **first login** (the setup wizard) — or, on a fresh
install, by `just wire`, which completes the wizard through its API and mints a `Kickstarrt` API key
([Service wiring → Automated wiring](wiring#automated-wiring)). From there
the two things that need configuring are the libraries — they point at the library dirs on the
shared bind (`/mnt/usenet/library/shows`, `/mnt/usenet/library/movies`) — and the transcode
policy, tuned for a CPU-only VPS.

> **Scanning is automatic.** `just wire` configures Sonarr/Radarr to push a library scan to
> Jellyfin whenever media is imported, upgraded, or renamed (the *arr → Jellyfin connections,
> library update on). You can still run **Scan All Libraries** manually at any time.

## 1. Libraries

No path mapping needed: the compose binds the whole shared tree into Jellyfin at its host path
(`- /mnt/usenet:/mnt/usenet`), so the library dirs and InfiniDysk's staging dir resolve at the same
places as in the \*arrs ([Service wiring](wiring#root-folders)).

Dashboard → **Libraries** → **Add Media Library**:

- **Content type** — Movies / Shows (or whatever your folder holds).
- **Folders** → **+** → add the library folder, e.g. `/mnt/usenet/library/shows` or
  `/mnt/usenet/library/movies`.
- Save, then **Scan All Libraries**.

## 2. Recommended settings for a streaming library

These settings apply to any Jellyfin whose media is fetched on demand rather than stored locally.
The exact labels can move between Jellyfin releases, but the goals are the same: let the media
manager announce changes, and avoid making Jellyfin write beside the media.

- **Real-time monitoring** — leave **on**. The library is made of ordinary `.strm` files in a
  normal directory, so filesystem events do fire. The \*arr → Jellyfin scan connection is still
  the reliable trigger; use **Scan All Libraries** for a manual catch-up scan.
- **Save artwork into media folders** — **off** unless you deliberately want artwork beside the
  media. The library dirs are the \*arr root folders, and sidecar images written into them clutter
  the import tree. Keep Jellyfin's metadata and artwork in its config directory.
- **Chapter images and trickplay** — optional. They make seeking nicer on compatible clients, but
  generating and storing them costs CPU, disk space, and scan time. Leave them off on a small VPS
  or enable them only for libraries and users that benefit from them.
- **TMDb API key** — consider adding your own key in Jellyfin's TMDb provider settings. It usually
  improves title, season, cast, and artwork matching for large or unusually named libraries and
  avoids relying entirely on the provider's shared rate limits. This is optional; it is a metadata
  API key, not a Usenet credential. Use a modest refresh schedule because metadata is local
  application state even though the media itself is remote, so large libraries can make the
  Jellyfin config directory grow.
- **Subtitles** — prefer text subtitles that the client can render. Image subtitles or subtitles
  that must be burned into the picture require video transcoding; that is especially expensive on
  a CPU-only server.

Do not add `/mnt/usenet/completed-downloads` as a library folder. It is InfiniDysk's staging area
for finished releases, not library content; the imported `.strm` files in
`/mnt/usenet/library/shows` and `/mnt/usenet/library/movies` are what Jellyfin should index.

## 3. Stack-specific playback settings

Also set Dashboard → **Playback** → **Transcoding path** to `/transcode` — a tmpfs, so
transcode scratch never touches disk. This stack transcodes in software (no GPU,
[FAQ](../faq#why-does-jellyfin-transcode-in-software-no-gpu)) and Recyclarr ships a **Direct
Play** quality profile, so the goal is to keep playback direct and never let a client push
the server into a CPU-only video transcode. The profile permits 4K/HEVC (every UHD release is
HEVC), so on clients without HEVC support the per-user policy below is what keeps the CPU idle:
remux plays, video re-encoding fails cleanly instead of transcode-spiking.

## 4. Transcode policy: no video transcoding, remux + audio transcoding stay on

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

If a library appears empty or a new import is missing:

1. Confirm the library points to `/mnt/usenet/library/shows` or `/mnt/usenet/library/movies`, not
   to the staging directory.
2. Run **Scan All Libraries** and check the Jellyfin log for a link it could not open.
3. Check the paths are visible inside the Jellyfin container:

   ```bash
   docker exec jellyfin ls -la /mnt/usenet/library/shows /mnt/usenet/library/movies
   ```

4. If an import exists but will not play, read the URL inside one `.strm` file and open it from the
   Jellyfin container (`docker exec jellyfin curl -fsSI <url>`). The link must resolve to
   InfiniDysk — see [InfiniDysk](infinidysk#troubleshooting).
