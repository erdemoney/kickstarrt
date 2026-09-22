<div align="center">

# kickst**Arr**t

**A public-IP media stack that runs itself.** Jellyfin + the \*arrs + a debrid gateway, served
directly on a `:443` edge, guarded by CrowdSec, terminated by Traefik — all defined in one repo
and brought up with a single command.

[![CI](https://img.shields.io/github/actions/workflow/status/erdemoney/kickstarrt-vps/ci.yml?logo=githubactions&logoColor=white&label=CI)](https://github.com/erdemoney/kickstarrt-vps/actions)
[![Docs](https://img.shields.io/badge/docs-wiki-blue?logo=readthedocs&logoColor=white)](https://erdemoney.github.io/kickstarrt-vps/)
[![Stack](https://img.shields.io/badge/stack-Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![TLS](https://img.shields.io/badge/tls-Let%27s%20Encrypt-2E8B57?logo=letsencrypt&logoColor=white)](https://letsencrypt.org)
[![WAF](https://img.shields.io/badge/waf-CrowdSec-brightgreen)](https://www.crowdsec.net)
[![Tooling](https://img.shields.io/badge/tooling-just-66459B)](https://just.systems)

</div>

---

kickst**Arr**t wires together everything a media library needs — **instant, debrid-based
streaming that keeps nothing on disk**, automatic TLS, and edge security — as code, on a VPS.
Direct Traefik `:443` ingress (Cloudflare is DNS-only — no video crosses its network), Tailscale
+ provider or UFW firewall controls, and no GPU.

## Architecture

```
              Internet                          Tailscale
                 │                                │
                 ▼                                ▼
  Cloudflare DNS (grey-cloud A records        tailnet IP :443
  + DNS-01 certs; no video traffic)           (100.x.y.z = TAILNET_IP)
                 │                                │
                 ▼                                ▼
  VPS public IP :443                           Traefik https-tailnet
  (ufw: 443 opened last;                        (panels + dashboard:
   :80 = https-redirect only,                   radarr sonarr prowlarr bazarr
   :22 = tailnet only)                          decypharr; tailnet-only, always on)
                 │                                │
                 ▼                                │
  Traefik https  ────► CrowdSec (WAF/blocking) ──┘
  (PUBLIC_BIND:443)
                 │
                 ▼
  Docker "internal" network
  ┌─────────────────────────────┐
  │ jellyfin     seerr          │   jellyfin + seerr are tailnet-only by default;
  │                             │   opt in with `just public enable <service>`
  │ radarr       sonarr         │
  │ prowlarr     bazarr         │   everything else (panels, dashboard):
  │ recyclarr    decypharr      │   https-tailnet only
  └─────────────────────────────┘
```

**The media loop:** Prowlarr finds releases → Sonarr/Radarr grab them → Decypharr resolves the
torrent against your debrid provider into instant FUSE files → the \*arrs symlink them into the
library → Jellyfin streams to any client. Zero local storage, immediately playable.

## Services

| Service     | Role |
| ----------- | ---- |
| `traefik`   | TLS edge & reverse proxy on `:443` — routes every hostname, issues the wildcard Let's Encrypt cert |
| `crowdsec`  | WAF / IP reputation — blocks scanners at the edge before they reach an app |
| `coredns`   | tailnet DNS — resolves `*.DOMAIN` to the box's tailnet address so admin panels work by name on the tailnet |
| `jellyfin`  | Media server & streaming to web, TV, and mobile clients |
| `seerr`     | User request manager — "want this movie" in one click |
| `radarr` / `sonarr` | Movies and TV automation — grabbing, renaming, library sync |
| `prowlarr`  | Indexer manager, synced to the \*arrs |
| `bazarr`    | Subtitle search & management |
| `recyclarr` | TRaSH-Guide sync — ships **Direct Play** (+ Sonarr **Direct Play (Anime)**) quality profiles, applied to Radarr/Sonarr automatically |
| `decypharr` | Debrid gateway — resolves grabs to instant FUSE streams |

## Key features

- **Nothing stored locally** — imports are symlinks into the debrid mount: instant,
  near-zero disk usage
- **Automatic TLS** — Traefik issues a `*.DOMAIN` Let's Encrypt wildcard via Cloudflare
  DNS-01; services can be opted into public HTTPS with `just public enable <service>`
- **Layered security** — Tailscale private administration, provider-firewall controls where
  available or host-firewall controls otherwise,
  Traefik TLS and entrypoint isolation, CrowdSec WAF, and application logins; `just health`
  checks the deployment without changing it
- **Private admin panels** — the \*arrs, Decypharr and the Traefik dashboard resolve by name
  *only on your tailnet* (CoreDNS + Tailscale split DNS): `https://radarr.<DOMAIN>` from any
  tailnet device, no public records, no extra login — the tailnet is the gate
  ([Tailnet DNS](https://erdemoney.github.io/kickstarrt-vps/tailnet))
- **Automated upkeep** — Renovate opens dependency PRs and CI validates every change (compose +
  pre-commit + a full secret-history scan)
- **One command to deploy** — `just init` fills the secrets, `just up` creates networks and
  config dirs and starts the stack; back it all up with the built-in restic recipes

## Quick start

> **Note:** this repo is meant to be **forked** (keep the fork **private**) and cloned onto the
> box. Get in over public SSH once, join the tailnet, and do all setup privately — public DNS
> records and `:443` open **last**. Secrets never touch the repo; they live in git-ignored
> `.env` files that `just init` creates. The full ordered walkthrough is the
> [Quickstart](https://erdemoney.github.io/kickstarrt-vps/quickstart).

```bash
curl -fsSL https://raw.githubusercontent.com/erdemoney/kickstarrt-vps/main/scripts/bootstrap.sh | sudo bash   # git, just, docker + tailscale join; prints your tailnet SSH address
git clone git@github.com:<you>/kickstarrt-vps.git && cd kickstarrt-vps
just init             # configures detected values and prompts for required/optional secrets (re-runs reconcile drift; 'just init --force' re-prompts)
just dns              # paste the printed nameserver into Tailscale (one-time; see Quickstart §7)
just up               # networks -> config dirs -> the whole stack; panels resolve on your tailnet immediately
```

After setup: point Jellyfin/Seerr at your debrid and \*arrs ([the docs](https://erdemoney.github.io/kickstarrt-vps/)),
then optionally enable public routers, add DNS records, and open the serving ports in your chosen firewall.

Requires [Docker](https://docs.docker.com/engine/install/) and
[just](https://just.systems/man/en/chapter_4.html) — your distro's package manager or a
[release binary](https://github.com/casey/just/releases). Both are installed by the bootstrap
script above, which also adds the invoking user to Docker's group.

## Docs

In reading order for a first deploy:

- [**Quickstart**](https://erdemoney.github.io/kickstarrt-vps/quickstart) — the ordered walkthrough: get in via Tailscale, choose the firewall, secrets, first boot, app setup, go public
- [**Security**](https://erdemoney.github.io/kickstarrt-vps/security) · [**Tailnet DNS**](https://erdemoney.github.io/kickstarrt-vps/tailnet) — the layered security model and its details
- [**Decypharr**](https://erdemoney.github.io/kickstarrt-vps/decypharr) · [**The \*arrs**](https://erdemoney.github.io/kickstarrt-vps/arrs) · [**Indexers**](https://erdemoney.github.io/kickstarrt-vps/indexers) · [**Services**](https://erdemoney.github.io/kickstarrt-vps/services) — the apps
- [**Additional services**](https://erdemoney.github.io/kickstarrt-vps/additional-services) · [**Ingress**](https://erdemoney.github.io/kickstarrt-vps/ingress) — extending the stack and the public edge
- [**Maintenance**](https://erdemoney.github.io/kickstarrt-vps/maintenance) · [**Updates & CI**](https://erdemoney.github.io/kickstarrt-vps/updates) — ongoing ops
- [**FAQ**](https://erdemoney.github.io/kickstarrt-vps/faq) — the design decisions, answered
- [**Oracle Cloud (free tier)**](https://erdemoney.github.io/kickstarrt-vps/oci) — appendix: free VPS from zero
