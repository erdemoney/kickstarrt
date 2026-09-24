set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

stack_list := shell("python3 -m scripts.stacks")
restic_image := "restic/restic:0.19.1"
hunt_image := "python:3.13-alpine3.22"

# Show available recipes
default:
    just --list

# Full first-time setup. The implementation lives in scripts/init.py so it can
# validate input and update env files atomically.

# Full first-time setup (idempotent; `just init --force` re-prompts).
[arg("force", long="force", value="--force", help="re-prompt optional secrets")]
init force="":
    python3 -m scripts.init {{ force }}

# The implementation lives in scripts/prepare.py.

# Create config dirs and `acme.json` (0600); called by `just up`.
[arg("dry_run", long="dry-run", value="--dry-run", help="report what would be done without changing anything")]
prepare dry_run="":
    python3 -m scripts.prepare {{ dry_run }}

# Read-only: never creates or edits a .env. Safe placeholder values are supplied
# through the shell environment for required deployment settings when they are not
# already set.

# Validate every compose file against the Docker Compose schema.
validate:
    @for s in {{ stack_list }}; do \
        echo "-- stacks/$s/compose.yaml" \
        && DOMAIN="${DOMAIN:-example.test}" \
           docker compose -f "stacks/$s/compose.yaml" config -q || exit 1 \
    ; done

# Create the shared Docker network (idempotent). The subnet is pinned inside
# 172.16.0.0/12 so the ufw-docker forward gate covers this network's egress
# with its default RFC1918 subnets when host-firewall mode is configured.
# Only change it if you re-provision the gate with `sudo ufw-docker install --docker-subnets`.

# Create the shared Docker network (idempotent). Add `--dry-run` to report the
# state without creating anything.
[arg("dry_run", long="dry-run", value="--dry-run", help="report the network state without creating it")]
networks dry_run="":
    #!/usr/bin/env bash
    set -euo pipefail
    if docker network inspect internal >/dev/null 2>&1; then
        echo "-- internal network already exists"
    elif [ -n "{{ dry_run }}" ]; then
        echo "-- network 'internal' would be created on subnet 172.30.0.0/16"
    else
        docker network create --subnet 172.30.0.0/16 internal
    fi

# Bring the whole stack up (ensures networks + config dirs exist first)
# `just prepare` creates the repo's data/ config directories.

# Bring the whole stack up (ensures networks + config dirs exist first).
# `just up --dry-run` previews the networks/prepare steps plus every stack's
# container plan without changing anything.
[arg("dry_run", long="dry-run", value="--dry-run", help="report what would be created and recreated without changing anything")]
up dry_run="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{ dry_run }}" ]; then
        just networks --dry-run
        just prepare --dry-run
    else
        just networks
        just prepare
    fi
    for s in {{ stack_list }}; do
        echo "-- $s"
        if [ -n "{{ dry_run }}" ]; then
            docker compose -f "stacks/$s/compose.yaml" up --dry-run
        else
            docker compose -f "stacks/$s/compose.yaml" up -d
        fi
    done

# Pull + recreate one service, searched across all stacks, e.g. `just update jellyfin`.
update service:
    #!/usr/bin/env bash
    set -euo pipefail
    found=0
    for s in {{ stack_list }}; do
        if docker compose -f "stacks/$s/compose.yaml" config --services | grep -qx "{{ service }}"; then
            echo "-- $s/{{ service }}"
            docker compose -f "stacks/$s/compose.yaml" pull "{{ service }}"
            docker compose -f "stacks/$s/compose.yaml" up -d "{{ service }}"
            found=1
            break
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "no service '{{ service }}' in any stack" >&2
        exit 1
    fi

# Update all containers to the images referenced in compose (pull + recreate changed ones)
update-all:
    @for s in {{ stack_list }}; do \
        echo "-- pulling $s" \
        && docker compose -f "stacks/$s/compose.yaml" pull || exit 1 \
    ; done
    @for s in {{ stack_list }}; do \
        echo "-- $s" \
        && docker compose -f "stacks/$s/compose.yaml" up -d || exit 1 \
    ; done

# Restart one stack, e.g. `just restart traefik`
restart stack:
    docker compose -f "stacks/{{ stack }}/compose.yaml" restart

# Stream logs for one stack, e.g. `just logs media-server`
logs stack:
    docker compose -f "stacks/{{ stack }}/compose.yaml" logs -f --tail=100

# Stream logs for one service (searched across all stacks), e.g. `just logs-svc jellyfin`
logs-svc service:
    #!/usr/bin/env bash
    set -euo pipefail
    for s in {{ stack_list }}; do
        if docker compose -f "stacks/$s/compose.yaml" ps --services | grep -qx "{{ service }}"; then
            exec docker compose -f "stacks/$s/compose.yaml" logs -f --tail=100 "{{ service }}"
        fi
    done
    echo "no service '{{ service }}' in any stack" >&2
    exit 1

# Open an interactive shell in a running service's container (searched across all
# stacks), e.g. `just shell jellyfin`. Tries bash first, falls back to sh for
# minimal images (alpine etc.) that lack it.

# Open an interactive shell in a running service's container.
shell service:
    #!/usr/bin/env bash
    set -euo pipefail
    cid=""
    for s in {{ stack_list }}; do
        if docker compose -f "stacks/$s/compose.yaml" ps --services 2>/dev/null | grep -qx "{{ service }}"; then
            cid=$(docker compose -f "stacks/$s/compose.yaml" ps -q "{{ service }}" 2>/dev/null || true)
            [ -n "$cid" ] || { echo "service '{{ service }}' is not running" >&2; exit 1; }
            break
        fi
    done
    if [ -z "$cid" ]; then
        echo "no service '{{ service }}' in any stack" >&2
        exit 1
    fi
    if docker exec -it "$cid" sh -c 'command -v bash >/dev/null 2>&1'; then
        exec docker exec -it "$cid" bash
    fi
    exec docker exec -it "$cid" sh

# Tear the whole stack down
down:
    @for s in {{ stack_list }}; do \
        echo "-- $s" \
        && docker compose -f "stacks/$s/compose.yaml" down || exit 1 \
    ; done

# This is also the entry point used by the optional overnight systemd timer.

# Pull the reviewed default branch, update changed containers, and verify the result.
[group('Maintenance')]
maintenance-run:
    python3 -m scripts.maintenance run

# Install the overnight maintenance systemd timer (default: 03:00 local time).
[group('Maintenance')]
maintenance-schedule ON_CALENDAR="*-*-* 03:00:00":
    python3 -m scripts.maintenance schedule "{{ ON_CALENDAR }}"

# Show the next maintenance run.
[group('Maintenance')]
maintenance-status:
    python3 -m scripts.maintenance status

# Stop and remove the maintenance timer.
[group('Maintenance')]
maintenance-unschedule:
    python3 -m scripts.maintenance unschedule

# Run one ephemeral, rate-limited Sonarr/Radarr back-catalog hunt.
[group('Maintenance')]
hunt-run MODE="both":
    HUNT_IMAGE="{{ hunt_image }}" exec python3 -m scripts.hunt run "{{ MODE }}"

# Install the ephemeral hunt systemd timer (default: 03:00 local time).
[group('Maintenance')]
hunt-schedule ON_CALENDAR="*-*-* 03:00:00":
    python3 -m scripts.hunt schedule "{{ ON_CALENDAR }}"

[group('Maintenance')]
hunt-status:
    python3 -m scripts.hunt status

[group('Maintenance')]
hunt-unschedule:
    python3 -m scripts.hunt unschedule

# Read-only host, firewall, DNS, and container health checks.
[group('Diagnostics')]
health:
    python3 -m scripts.health

# Reconcile the stable cross-service wiring through the applications' REST APIs,
# including Seerr's first-login bootstrap and its Jellyfin/Radarr/Sonarr links.
# Interactive by default: each service-level change is displayed and requires
# confirmation. Use `just wire --dry-run` to preview or `just wire --yes` only
# when the plan has already been reviewed. API calls run from the containers so
# Docker's private service names remain usable without publishing new ports.

# Reconcile the stable cross-service wiring through the applications' REST APIs.
[arg("yes", long="yes", value="--yes", help="apply all planned changes without prompting")]
[arg("dry_run", long="dry-run", value="--dry-run", help="discover and display changes without applying them")]
[group('Integrations')]
wire dry_run="" yes="":
    python3 scripts/wire.py {{ dry_run }} {{ yes }}

# This deliberately does not change UFW rules or DNS records.

# Enable or disable public Traefik routers without editing Compose files.
# `just public --dry-run enable <svc>` previews the router change; UFW and DNS
# are never touched either way.
[arg("dry_run", long="dry-run", value="--dry-run", help="report what would change without editing .env or recreating services")]
[group('Security')]
public dry_run="" action *SERVICES:
    python3 -m scripts.public {{ dry_run }} {{ action }} {{ SERVICES }}

# Show the tailnet DNS resolver setup (CoreDNS in the traefik stack).
# The matching Tailscale admin setting is one-time: DNS -> Nameservers -> add
# TAILNET_IP:53, restricted to DNS -> the domain only (see docs/tailnet.md).

# Show the tailnet DNS resolver setup (CoreDNS in the traefik stack).
[group('Security')]
dns:
    #!/usr/bin/env bash
    set -euo pipefail
    T=$(sed -n 's|^TAILNET_IP=\(.*\)|\1|p' stacks/traefik/.env | tail -n1)
    D=$(sed -n 's|^DOMAIN=\(.*\)|\1|p' stacks/traefik/.env | tail -n1)
    echo "resolver : $T:53  (CoreDNS container in the traefik stack)"
    echo "serves   : *.$D -> $T     (tailnet only; see docs/tailnet.md)"
    echo "console  : Tailscale DNS -> Nameservers -> custom $T, restricted to $D"
# Encrypted, deduplicated repo backups with restic, run in a container (nothing to
# install). Documented backend is Cloudflare R2 (see how-to in the wiki); `.env.restic`
# is configured by `just init` (R2_ACCOUNT_ID / R2_BUCKET / AWS creds -> RESTIC_REPOSITORY
# + RESTIC_PASSWORD; `AWS_DEFAULT_REGION=auto` is required for R2). Deviating is one edit
# in .env.restic - RESTIC_REPOSITORY selects any backend (local, sftp:, s3:, b2:, rclone: ...)
# and RESTIC_PASSWORD encrypts it; everything in that file is forwarded via docker run
# --env-file, so backend credentials added there are forwarded too. Scope: the repo working
# tree - every .env plus data/ (where all app config state lives). Configure .env.restic with `just init`, or copy
# .env.restic.example by hand.
# Initialize the restic repository (idempotent).
[group('Backups')]
backup-init:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup init

# Snapshot the repo working tree with restic.
[group('Backups')]
backup:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup backup

# List restic snapshots.
[group('Backups')]
backup-list:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup list

# Verify restic repository integrity.
[group('Backups')]
backup-check:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup check

# Forget + prune old snapshots per RESTIC_KEEP_*.
[group('Backups')]
backup-prune:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup prune

# Dry-run preview, then restore restic snapshots.
[group('Backups')]
backup-restore SNAPSHOT="latest":
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup restore "{{ SNAPSHOT }}"

# Install a systemd timer for daily backup + prune.
[group('Backups')]
backup-schedule ON_CALENDAR="daily":
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup schedule "{{ ON_CALENDAR }}"

# Stop and remove the backup timer.
[group('Backups')]
backup-unschedule:
    RESTIC_IMAGE="{{ restic_image }}" exec python3 -m scripts.backup unschedule
