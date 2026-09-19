---
title: Decypharr
nav_order: 5
---

# Decypharr (debrid gateway)

Decypharr mounts your debrid provider as a FUSE filesystem, so Sonarr/Radarr see instant debrid
files for streaming rather than locally downloaded media. It runs from the media-server stack
with the FUSE plumbing already in the compose
(`/mnt/debrid:/mnt:rshared`, `/dev/fuse`, `SYS_ADMIN`, `apparmor:unconfined`) — nothing to
add.

## First-run setup wizard

Visit `https://decypharr.<DOMAIN>` once, over the tailnet ([Quickstart §9](quickstart#9-set-up-the-apps)).
Wizard order:

1. **Authentication** — create the admin username/password. The **API token shown once** after
   setup completes is Decypharr's *own* API credential: save it (regenerates via
   `POST /api/refresh-token`). It is **not** the credential used by the \*arr integrations —
   those use each app's own API key ([The \*arrs](arrs)).
2. **Debrid account** — add at least one provider (Real-Debrid, AllDebrid, Debrid-Link,
   Torbox, Premiumize) with its API key; Torbox also provides Usenet ([Services](services)).
3. **Download Folder Path** — `/mnt/downloads` — where Decypharr stages the symlinks the \*arrs
   import. It's a real directory on the shared bind — a sibling of the library root folders, not
   a subpath of the mount: the DFS root is read-only, so `mkdir` under `/mnt/decypharr/*` fails
   ([The \*arrs](arrs#imports-are-symlinks-not-hardlinks)).
4. **Mount System** — pick **DFS**, mount path `/mnt/decypharr` (what the \*arrs import from),
   and a cache dir. Keep the **Cache Directory** default `/tmp/decypharr-cache`: it's a
   disposable chunk cache (re-warms on demand; wiping it on redeploys costs nothing) and
   keeping it in the container keeps it out of restic backups and the `data/` config dir. Don't point
   it at the FUSE mount `/mnt/decypharr` (it would recurse into debrid) or at a tmpfs/RAM (a
   chunk cache is sized in GB — RAM is for Jellyfin's transcode). Cap the **Disk Cache Size**
   at a few GB so the rolling cache can't fill the system disk.

Outside the wizard: the mount root is a **read-only virtual filesystem** — Decypharr's own
provider folders and virtual folders — so
`mkdir` under `/mnt/decypharr/*` fails with `Operation not supported`, even as root. The \*arr
**root folders** and Decypharr's **download folder** are all plain siblings of the mount on the
shared bind, not subpaths of it: Sonarr → `/mnt/shows`, Radarr → `/mnt/movies`, staging →
`/mnt/downloads` (`just prepare` creates and owns all three to `ENV_PUID`/`ENV_PGID`).
Jellyfin's libraries point at the same folders
([Jellyfin](jellyfin#1-libraries)).

Config is written to `data/decypharr/configs/config.json`.

## Integration with Sonarr/Radarr

The wiring has two sides; the \*arr-UI side (streaming integration and root folders) is documented
in [The \*arrs](arrs). Decypharr's own side:

- **Outbound** — Decypharr → Settings → **Arrs**: it auto-detects apps that hit it; give each
  arr's host (`http://sonarr:8989`, never the public URL) and API key.
- **Repair worker / queue cleanup** — enable in Settings → Arrs (the blacklist + research
  defaults are sensible) so failed grabs don't clog the queue.

No **path mapping** is needed in this stack: Decypharr's mount path and the arrs' bind are
the same absolute path (`/mnt/decypharr`), so the path it reports is the path they can open.
Add a remote path mapping only if you deviate — a different mount path in Decypharr's config,
a different container path in the bind, or Decypharr on another host.

## Visibility of the mount

Decypharr creates its FUSE mount *inside* its own container; `:rshared` pushes it out to the
host at `/mnt/debrid/decypharr`, and `jellyfin`/`sonarr`/`radarr`/`bazarr` receive it with
`:rslave`. Both halves ship in the compose. Two rules make that work, and both are easy to
get wrong if you ever edit the binds:

- **Bind the parent, not the mountpoint.** Consumers bind `/mnt/debrid` (as `/mnt`), not
  `/mnt/decypharr:/mnt/decypharr`. A mount appearing *at* `/mnt/decypharr` belongs to its
  parent mount, so it propagates to anyone watching the parent — but a bind of the
  mountpoint itself captures whatever was there at container start and never sees the FUSE
  mount arrive.
- **The flags are asymmetric.** The producer shares (`:rshared`); the consumers receive
  (`:rslave`). A plain bind with no flag propagates nothing in either direction.

The indirection through the dedicated host directory `/mnt/debrid` (bound in *as* `/mnt`)
keeps the containers from ever seeing the host's real `/mnt` — backup drives or other disks
mounted there stay invisible to five media containers that would otherwise hold them
read-write.

The net effect: **no startup order to respect** — consumers can boot before Decypharr and the
mount appears inside them when it's created; restarting Decypharr re-propagates instead of
leaving the others with a stale `Transport endpoint is not connected` handle.

Host prep is handled by **`just prepare`** (before the stack's first `just up`): it creates the
host bind tree `/mnt/debrid`, its DFS mountpoint (`/mnt/debrid/decypharr`), the \*arr library
dirs and Decypharr's download folder (`/mnt/debrid/shows`, `/mnt/debrid/movies`,
`/mnt/debrid/downloads`), owning all of them to `ENV_PUID`/`ENV_PGID`
from `stacks/media-server/.env`. Sudo only fires when a target is actually
missing or mis-owned — normal `just up` runs are prompt-free, and a re-run when the mount is live
leaves it alone. Never run a manual `chown -R` over
`/mnt/debrid` — on a live stack that recurses straight into the FUSE mount. Two things make DFS
mount instead of silently failing:

- **The mountpoint must be writable by the stack user before the mount.** If it's root-owned,
  `fusermount3` refuses with `user has no write access to mountpoint` and no mount appears.
- **FUSE needs setuid.** The decypharr service deliberately does **not** inherit the stack-wide
  `security_opt: no-new-privileges` (see the compose comment): Decypharr mounts via setuid
  `/usr/bin/fusermount3`, and with `no_new_privs` the privilege raise is blocked and the mount
  dies with `fusermount3: mount failed: Operation not permitted` — the mount never appears and
  the \*arrs reject every root folder as `not writable by user 'abc'`.

If a consumer comes up empty (`/mnt/decypharr` shows nothing inside a container), check the two
mount-propagation rules above; if the mount is simply missing, verify it first:

```bash
docker exec decypharr sh -c 'grep -w decypharr /proc/mounts'   # a DFS entry must exist
docker compose -f stacks/media-server/compose.yaml logs --tail=40 decypharr  # or find the [dfs] error here
sudo fusermount -u -z /mnt/debrid/decypharr  # clear a stale mountpoint after an unclean kill
findmnt -o TARGET,PROPAGATION /mnt/debrid    # want "shared"; systemd makes / rshared at boot,
sudo mount --make-rshared /mnt/debrid        # so this fix is rarely needed
```

## Reference

- Decypharr docs: <https://decypharr.com/guides> (wizard, arr integration, mounts,
  troubleshooting)
