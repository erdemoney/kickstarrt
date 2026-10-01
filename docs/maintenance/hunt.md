---
title: Back-catalog hunting
parent: Maintenance
nav_order: 2
---

# Back-catalog hunting

The repository includes a small job that asks Sonarr and Radarr to search for
monitored missing items and files below their quality cutoffs. It does not replace either
application, download anything itself, or expose a web interface. Each run launches the repo's
`scripts/hunt.py` inside an ephemeral container from a pinned stock `python` image, then removes
the container.

## Setup

`just init` creates a private `.env.hunt` from `.env.hunt.example`. The launcher reads each enabled
app's API key from its host-side config (`data/sonarr/config.xml` or `data/radarr/config.xml`) and
passes the key to the ephemeral hunt container for that run. Start each app once before enabling it
so its config file exists. Hunt settings belong in `.env.hunt`, not `stacks/media-server/.env`.

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

Choose the search mode with `just hunt-run [missing|upgrades|both]` (default: `missing`). Configure
the optional settings below in `.env.hunt`.

| Variable | Default | Purpose |
| --- | ---: | --- |
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
