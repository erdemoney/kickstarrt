---
title: Back-catalog hunting
nav_order: 20
---

# Back-catalog hunting

The repository includes a small job that asks Sonarr and Radarr to search for
monitored missing items and files below their quality cutoffs. It does not replace either
application, download anything itself, or expose a web interface. Each run launches the repo's
`scripts/hunt.py` inside an ephemeral container from a pinned stock `python` image, then removes
the container.

## Setup

Copy the two API keys from **Settings -> General -> Security** in Sonarr and Radarr into
`stacks/media-server/.env`:

```text
HUNT_SONARR_API_KEY=...
HUNT_RADARR_API_KEY=...
```

The state file is kept at `data/hunt/state.json`. The container itself is removed after every run.

## Run

```bash
just hunt-run both
just hunt-run missing
just hunt-run upgrades
```

Missing searches run before upgrades. Each accepted search is recorded in the state file and is
not retried until `HUNT_COOLDOWN_DAYS` has elapsed. Items that have since downloaded naturally
drop out of the next scan.

## Controls

| Variable | Default | Purpose |
| --- | ---: | --- |
| `HUNT_MODE` | `both` | `missing`, `upgrades`, or `both` |
| `HUNT_SONARR` | `true` | Enable Sonarr |
| `HUNT_RADARR` | `true` | Enable Radarr |
| `HUNT_MISSING_BATCH_SIZE` | `10` | Items per missing search command |
| `HUNT_UPGRADE_BATCH_SIZE` | `5` | Items per upgrade search command |
| `HUNT_DELAY_SECONDS` | `60` | Delay between submitted batches |
| `HUNT_MAX_ITEMS_PER_RUN` | `100` | Maximum items considered per run |
| `HUNT_MAX_QUEUE_SIZE` | `0` | Pause an app at this queue size; `0` disables the check |
| `HUNT_COOLDOWN_DAYS` | `7` | Retry cooldown for an accepted search |

## Scheduling

```bash
just hunt-schedule
just hunt-status
just hunt-unschedule
```

Override the default schedule with a systemd calendar expression:

```bash
just hunt-schedule 'Mon,Wed,Fri 03:00:00'
```
