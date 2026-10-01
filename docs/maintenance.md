---
title: Maintenance
nav_order: 16
has_children: true
---

# Maintenance

Day-to-day operations for updating, checking, and operating the host. For encrypted snapshots and
restores, see [Backups](maintenance/backups); for GitHub automation and CI, see
[Updates & CI](maintenance/updates).

## Ops recipes (`justfile`)

| Command | What it does |
| --- | --- |
| `just init` | Create or reconcile `.env` files and fill interactive secrets. |
| `just up` / `just down` | Start or stop every stack. `just up --dry-run` previews changes. |
| `just update-all` / `just update <svc>` | Pull fresh images and recreate changed containers, or update one service. |
| `just maintenance-run` | Fast-forward Git, update all stacks, then run health checks. |
| `just maintenance-schedule` | Install the overnight maintenance timer (default: 03:00 host-local time). |
| `just maintenance-status` / `just maintenance-unschedule` | Inspect or remove the maintenance timer. |
| `just health` | Read-only host, firewall, DNS, and container health panel. |
| `just logs <stack>` / `just logs-svc <svc>` | Tail logs for a stack or service. |
| `just restart <stack>` | Restart a stack. |
| `just validate` | Run `docker compose config -q` on every stack without writing `.env` files. |
| `just prepare` | Create config directories and `acme.json` (called by `just up`; supports `--dry-run`). |
| `just wire` | Reconcile app integrations through APIs; use `--dry-run` to preview. |
| `just dns` | Print the Tailscale split-DNS resolver setup (see [Tailscale](tailscale)). |
| `just networks` | Create the shared `internal` network; supports `--dry-run`. |
| `just public enable <svc>` / `just public disable <svc>` | Change a service's public Traefik router, without changing DNS or firewall rules. |
| `just public status` | Show which services are tailnet-only or also routed publicly. |

The deployable stack inventory lives in `stacks/manifest.txt`. Add a stack there only after its
Compose file and configuration are ready; lifecycle commands, health checks, and CI then include it.

Formatting and linting use **pre-commit** (`pre-commit install` once). The hooks check YAML/JSON,
formatting, large files, merge markers, case conflicts, private keys, and staged secrets; CI runs
the same checks plus a full-history secret scan.

## Scheduled maintenance

The optional systemd timer applies merged Renovate updates during a quiet window. Its default is
03:00 **host-local time**; the timer runs on the host and follows the VPS time zone
([Quickstart](quickstart#set-the-boxs-time-zone)).

```bash
just maintenance-schedule
just maintenance-status
```

Choose another systemd calendar expression when needed:

```bash
just maintenance-schedule "*-*-* 04:30:00"
```

Each run requires a clean Git worktree, uses `git pull --ff-only`, updates the stacks, and verifies
Docker plus every expected container. A lock prevents unattended and manual runs from overlapping.
Missed runs are not replayed after downtime. Inspect output with:

```bash
journalctl -u kickstarrt-maintenance.service
```

Remove the timer with `just maintenance-unschedule`. If a run fails, inspect the journal and run
`just maintenance-run` after resolving the issue; automatic rollback is not attempted.

This updates the repository and container images only. Keep the host operating system, Docker
Engine, Compose plugin, kernel, and other system packages current separately through the host
distribution's package manager. For hosts using UFW mode, `ufw-docker` is pinned to release tag
`251123` in the [UFW setup instructions](quickstart#ufw-mode) and is not managed by Renovate;
update it deliberately when [upstream](https://github.com/chaifeng/ufw-docker/releases) publishes
a newer release.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Renovate opened no PRs | See [Updates & CI](maintenance/updates#troubleshooting). |
| New indexer or app link fails | Check the URL and port against [Service wiring](services/wiring); revisit the API key. |
| InfiniDysk download client test fails | The Arr client and InfiniDysk must share `FRONTEND_BACKEND_API_KEY`; see [InfiniDysk](services/infinidysk#troubleshooting). |
| Direct Play profile missing | Check `docker logs recyclarr`; if an Arr API key changed, run `just wire`. |
| CrowdSec bouncer is not blocking | Recreate CrowdSec and Traefik after a key change; inspect `cscli bouncers list`. |
| Traefik won't start after a repo change | First start downloads plugins; check outbound internet and run `just validate`. |
| One container has a problem | Try `just update <svc>` after a tag bump rather than taking down the stack. |

For operational DNS and edge checks, see [CoreDNS](services/coredns), [CrowdSec](services/crowdsec),
and [Traefik](services/traefik).
