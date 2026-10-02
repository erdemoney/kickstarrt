---
title: Backups
parent: Maintenance
nav_order: 1
---

# Backups

This is a streaming stack: the host holds configuration and application state, not media. The
repo's `data/` directory contains Traefik configuration and application state, including the
*arr databases, InfiniDysk's SQLite database, and Maintainerr's rules and settings. The media itself
remains on the Usenet provider;
the library can be rebuilt by searching and importing it again.

## Offsite restic backups

Local snapshots cover application state. Back up the repository working tree too: `stacks/*/.env`
contains secrets and `data/` contains runtime configuration. The `just` recipes run
[restic](https://restic.net) in a container, with Cloudflare R2 as the documented backend.

One-time setup:

```bash
just init          # answer yes to the R2 restic step, or configure .env.restic by hand
just backup        # initialize the repository on first run, then snapshot the repository
just backup-schedule   # optional daily systemd timer (backup + prune)
```

### Cloudflare R2

1. In [Cloudflare R2](https://dash.cloudflare.com/?to=/:account/r2/overview), create a bucket (for
   example `media-server-restic`).
2. Create a User API Token with **Object → Read & Write** permission. Save its Access Key ID and
   Secret Access Key, and note the Cloudflare Account ID.
3. Run `just init` and answer yes to the R2 backup prompt. It writes `.env.restic` with the account,
   bucket, credentials, and encryption password. `AWS_DEFAULT_REGION` must remain `auto` for R2.

Alternatively, copy `.env.restic.example` to `.env.restic` and fill in the same values manually.
The `.env.restic` file is passed to the container with `docker run --env-file`.

### Other backends

Any network-accessible backend supported by restic can be used by setting `RESTIC_REPOSITORY` and
the matching credentials in `.env.restic`.

| Backend | Example `RESTIC_REPOSITORY` |
| --- | --- |
| Backblaze B2 | `b2:my-bucket:my-path` |
| S3-compatible | `s3:s3.amazonaws.com/my-bucket` |
| Azure / GCS | `azure:container:/path` / `gs:bucket:/path` |
| rclone | `rclone:remote:path` |

Local-directory and SFTP repositories need their paths or keys mounted into the restic container;
the provided recipes do not configure those mounts.

## Snapshot operations

| Command | What it does |
| --- | --- |
| `just backup-list` | List snapshots. |
| `just backup-check` | Verify repository integrity. For a full audit, run `restic check --read-data` manually. |
| `just backup-prune` | Forget and prune snapshots using `RESTIC_KEEP_*` in `.env.restic`. |
| `just backup-restore [<id>]` | Preview, then restore into the repository working tree (default: latest). |
| `just backup-schedule [<cal>]` | Install a systemd timer for backup then prune (default: daily; requires sudo). |
| `just backup-unschedule` | Remove the installed backup timer. |

The systemd timer captures output in journald and uses `Persistent=true` to catch up a skipped
backup. Each run prunes only after a successful backup, keeping snapshots within the configured
`RESTIC_KEEP_*` policy:

```bash
just backup-schedule                     # daily
just backup-schedule "*-*-* 04:30:00"    # custom calendar expression
systemctl list-timers kickstarrt-restic-backup.timer
```

On a host without systemd, use cron or its scheduler. The equivalent daily cron command is:

```cron
0 4 * * * cd /srv/kickstarrt && /usr/local/bin/just backup && /usr/local/bin/just backup-prune
```

`just backup-restore` dry-runs first and asks before writing. It keeps files absent from the
snapshot, overwrites restored files in place, and restores the repository working tree including
`data/` and `.env` files. `.env.restic` survives restores. Periodically test a restore into a scratch
clone.

> **Protect the working tree and password.** Do not run `git clean` on the server: ignored files
> include the `data/` state. Keep `RESTIC_PASSWORD` safe separately; without it the repository
> cannot be recovered. Keep the worktree clean before restoring so tracked files do not become
> unexpected diffs.
