---
title: Maintenance
nav_order: 16
---

# Maintenance and day-to-day ops

## Ops recipes (`justfile`)

| Command                         | What it does                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------- |
| `just init`                     | create/reconcile `.env` files and fill interactive secrets (idempotent)           |
| `just up`                       | create networks, config dirs, `acme.json`, then bring up every stack; use `--dry-run` to preview |
| `just down`                     | tear every stack down                                                             |
| `just update-all`               | pull fresh images + recreate changed containers                                   |
| `just update <svc>`             | pull + recreate one service, searched across all stacks, e.g. `just update jellyfin` |
| `just maintenance-run`          | fast-forward Git, update all stacks, then run the health checks                   |
| `just maintenance-schedule`     | install the overnight maintenance timer (default: 03:00 local time)              |
| `just maintenance-status`       | show the next maintenance run                                                     |
| `just maintenance-unschedule`   | stop and remove the maintenance timer                                             |
| `just health`                   | read-only host, firewall, DNS, and container health panel                         |
| `just logs <stack>`             | tail logs for a stack                                                             |
| `just logs-svc <svc>`           | tail logs for one service, e.g. `just logs-svc jellyfin` (found across all stacks) |
| `just restart <stack>`          | restart a stack                                                                   |
| `just validate`                 | `docker compose config -q` on every stack (read-only — never writes a `.env`)     |
| `just prepare`                  | create config dirs and `acme.json` (0600) (called by `just up`); use `--dry-run` to preview what would change |
| `just wire`                     | interactively reconcile Arr root folders, the **InfiniDysk (Usenet)** download clients and the matching InfiniDysk Arr registrations, Prowlarr's app links, Bazarr connections, Recyclarr secrets, and the Sonarr/Radarr → Jellyfin scan connections (creating the Jellyfin admin/API key on first run, or minting the key from existing admin credentials) through REST APIs; use `--dry-run` to preview |
| `just dns`                      | print the tailnet DNS resolver setup (see [Tailnet DNS](tailnet))                 |
| `just networks`                 | create the shared `internal` network (pinned subnet `172.30.0.0/16`); use `--dry-run` to report the state without creating it |
| `just public enable <svc>` / `just public disable <svc>` | enable or remove a service's public Traefik router; does not change UFW or DNS; use `--dry-run` to preview |
| `just public status`            | show which services are tailnet-only or also routed publicly     |
| `sudo ufw status verbose`       | inspect the host firewall rules when using UFW mode; provider firewalls must be checked in the provider console (see [Quickstart §6](quickstart#6-choose-the-firewall-model)) |
| `sudo ufw-docker check`         | verify the Docker forward gate when using UFW mode (see [ufw-docker](https://github.com/chaifeng/ufw-docker)) |
| `just backup-init`              | create the restic repository in `RESTIC_REPOSITORY` (idempotent; see below)       |
| `just backup` / `backup-list` / `backup-check` / `backup-prune` / `backup-restore` | restic snapshots, integrity, retention, restore — see below |

The deployable stack inventory lives in `stacks/manifest.txt`. Add a stack there only after its
Compose file and configuration are ready; `just up`, `just down`, updates, health checks, and CI
will then include it automatically.

Formatting and linting are handled by **pre-commit** directly (`pre-commit install` once, then
hooks run automatically on every commit). The hooks cover YAML/JSON syntax and formatting,
large files, merge markers, case conflicts, private keys and staged-secret scanning; CI runs
the same set plus a full-history secret scan. Gitleaks is auto-downloaded by pre-commit on
first run.

The update flow the repo is built around: Renovate opens a PR → CI and review → merge → the
overnight maintenance timer runs `git pull --ff-only`, `just update-all`, and a deployment health
check (see [Updates](updates)). `just maintenance-run` runs the same flow immediately.

This updates the repository and container images only. Keep the host operating system, Docker
Engine, Compose plugin, kernel, and other system packages up to date separately through the
host distribution's package manager.

One exception: `ufw-docker` (installed by the `bootstrap` script) is pinned to release tag
`251123` in `scripts/bootstrap.sh` and is invisible to Renovate — bump that tag deliberately
via PR when [upstream](https://github.com/chaifeng/ufw-docker/releases) publishes a newer release.

### Scheduled maintenance

The optional systemd timer applies merged Renovate updates during a quiet window. Install it with
the default schedule of 03:00 in the server's local timezone:

```
just maintenance-schedule
```

Choose another systemd calendar expression when needed:

```
just maintenance-schedule "*-*-* 04:30:00"
just maintenance-status
```

Each run requires a clean Git worktree, uses `git pull --ff-only`, updates the stacks, and verifies
Docker plus every expected container. A lock prevents an unattended run from overlapping a manual
`just maintenance-run`. The timer does not catch up missed runs after downtime, avoiding an
unexpected daytime deployment. Output is available with:

```
journalctl -u kickstarrt-maintenance.service
```

Remove the timer with `just maintenance-unschedule`. If a run fails, inspect the journal and run
`just maintenance-run` manually after resolving the issue; this first version deliberately does
not attempt an automatic rollback.

## Backups

This is a streaming stack — the host holds no media, only config, so the whole backup story is
one target: the **config directory** — the repo's `data/` dir (`acme.json`, the
Traefik configs, and each app's own state like the \*arr databases and InfiniDysk's SQLite
database). Nothing in compose is precious — any container is one `just up` from a clean slate. The
config directory is the only state you can't rebuild; if you snapshot exactly one thing, snapshot
that. The media itself needs no backup: it lives on your Usenet provider, and the library is
rebuilt by re-downloading from the indexers if the host is ever lost.

### Offsite restic backups of the repo

Local snapshots cover the config state; the other state that can't be rebuilt from `main` is
the **repo working tree itself** — `stacks/*/.env` hold every secret and `data/` holds
runtime config. Back it up too, encrypted and deduplicated, with
[restic](https://restic.net), run in a container by `just` (nothing to install). One-time
setup:

```
just init          # answer yes to the R2 restic step (or copy .env.restic.example -> .env.restic by hand)
just backup-init   # create the restic repository (idempotent)
just backup        # snapshot the repo; schedule it daily via a systemd timer or cron
```

`.env.restic` is passed to the container with `docker run --env-file`. `just init` configures
it for the documented backend, **Cloudflare R2** — zero egress, no minimums, same account as
the rest of this stack. (Backblaze B2 is cheaper raw storage; every backend works, but you're
on your own if you deviate — see below.)

#### Cloudflare R2 (the documented path)

1. Open [Cloudflare R2](https://dash.cloudflare.com/?to=/:account/r2/overview) → **Create bucket** (e.g. `media-server-restic`; location
   Automatic).
2. **R2** → [**Manage R2 API Tokens**](https://dash.cloudflare.com/?to=/:account/r2/api-tokens)
   → **Create API token** → type **User API Token**, permission **Object → Read & Write**
   (Admin is more than restic needs; read-only breaks `just backup-prune`). Save the
   **Access Key ID** and **Secret Access Key**, and note your **Account ID** (R2 page, scroll
   down: **Usage → Account Details**).
3. Run `just init` and answer **yes** to "Configure Cloudflare R2 restic backups now?" — it
   prompts for the Account ID, bucket, access key, secret key, and encryption password, then
   writes `.env.restic`:

   ```
   RESTIC_REPOSITORY=s3:https://<ACCOUNT_ID>.r2.cloudflarestorage.com/<BUCKET>
   RESTIC_PASSWORD=...
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_DEFAULT_REGION=auto
   ```

   `AWS_DEFAULT_REGION` must stay `auto` — it's R2's only region. To configure by hand
   instead of re-running init, copy `.env.restic.example` to `.env.restic` and fill the same
   values.

#### Other backends (on you)

Any backend restic reaches over the network works with these recipes unchanged — set
`RESTIC_REPOSITORY` and the matching credentials yourself. (A `local dir`, `sftp:` or
`rclone:` repository additionally needs its path, key or config mounted into the restic
container, which the recipes don't do.)

| Backend       | `RESTIC_REPOSITORY` example               |
| ------------- | ----------------------------------------- |
| Backblaze B2  | `b2:my-bucket:my-path` (cheapest storage) |
| local dir     | `/mnt/backups/restic`                     |
| SFTP          | `sftp:user@host:/srv/restic`              |
| S3-compatible | `s3:s3.amazonaws.com/my-bucket`           |
| Azure / GCS   | `azure:container:/path` / `gs:bucket:/path` |
| rclone        | `rclone:remote:path`                      |

Credential vars live in `.env.restic` too (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`, `RCLONE_CONFIG`, ...) and are forwarded the same way.
Snapshots take the whole working tree — including `.git`, `.env.restic`, and every ignored file. Keep
`RESTIC_PASSWORD` somewhere safe separately: without it the repository is unrecoverable.

Other recipes:

| Command                     | What it does                                               |
| --------------------------- | ---------------------------------------------------------- |
| `just backup-list`          | list snapshots                                             |
| `just backup-check`         | verify repository integrity (for a full audit run `restic check --read-data` manually) |
| `just backup-prune`         | `forget --prune` honoring `RESTIC_KEEP_*` in `.env.restic` |
| `just backup-restore [<id>]`| dry-run preview, then restore into the repo working tree (default: latest) |
| `just backup-schedule [<cal>]`| install a systemd timer running `just backup` then `just backup-prune` (default `daily`; sudo) |
| `just backup-unschedule`    | stop and remove the installed systemd timer (sudo)         |

Schedule the routine snapshots with a **systemd timer** — better than cron here: journald
captures the output, and `Persistent=true` catches up on a backup that was skipped while the
host was off. (`just backup` alone still snapshots without pruning; use `just backup-prune`
by hand, or let the timer do both.)

```bash
just backup-schedule                     # runs daily
just backup-schedule "*-*-* 04:30:00"    # custom calendar, re-run to change
```

This writes `kickstarrt-restic-backup.{service,timer}` under `/etc/systemd/system` via sudo
(with a confirmation prompt), resolves your actual `just` path into `ExecStart`, and enables
the timer. Each run **backs up, then prunes**: `backup-prune` runs only after a successful
backup, so snapshots are retained per `RESTIC_KEEP_*` and pruned automatically — no need to
SSH in to keep storage bounded. On a host **without** systemd (Alpine, OpenWrt, a NAS
scheduler), it prints the equivalent cron line and exits non-zero — or use cron directly:

```
0 4 * * * cd /srv/kickstarrt && /usr/local/bin/just backup && /usr/local/bin/just backup-prune
```

`systemctl list-timers kickstarrt-restic-backup.timer` shows the next run;
`just backup-unschedule` removes the units.

`just backup-restore` is **non-destructive**: it dry-runs first, prints exactly what would be
restored/updated, and asks for confirmation before writing anything. Files present locally
but missing from the snapshot are kept (no `--delete`); restored files overwrite current ones
in place. It re-creates the repo working tree (`data/` + all `.env` files); `.env.restic`
survives restores. Drill a restore into a scratch clone periodically — an untested backup is
a gamble. Note the offsite-repo point: all app config lives in the repo's own `data/` dir, so a
restic snapshot already covers everything this host can't rebuild; the R2 repository exists
for the case local snapshots can't help — the box itself disappearing.

> **`data/` is untracked app state.** Never `git clean` on the server — `-dfx` removes
> ignored files, i.e. the whole config state. `git pull`/`reset --hard` are safe (they only
> touch tracked files). And keep the working tree clean (no uncommitted changes) before
> `just backup-restore`, otherwise restored versions of the tracked `data/traefik/*.yml`
> show up as diffs.

## Troubleshooting

| Symptom                                      | Fix                                                                            |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| Renovate opened no PRs                       | see [Updates](updates) troubleshooting                                         |
| New indexer/app link fails                   | check the URL+port against the [internal DNS table](services/wiring); revisit the API key |
| InfiniDysk download client test fails        | the Arr client and InfiniDysk must share `FRONTEND_BACKEND_API_KEY`; see [InfiniDysk](services/infinidysk#troubleshooting) |
| Direct Play / Direct Play (Anime) profile missing in Radarr/Sonarr | `docker logs recyclarr`; if an arr's API key was regenerated, run `just wire` |
| Bouncer not blocking                         | recreate crowdsec + traefik after a key change; `cscli bouncers list`          |
| Traefik won't start after this repo's change | first start downloads plugins — check outbound internet; `just validate` first |
| Something in one container only              | `just update <svc>` after a tag bump, don't `down` the stack                   |
