<div align="center">

# kickst**Arr**t

**A public-IP media stack that runs itself.** Jellyfin + the \*arrs + a Usenet streaming gateway,
served directly on a `:443` edge, guarded by CrowdSec, terminated by Traefik — all defined in one
repo and brought up with a single command.

[![CI](https://img.shields.io/github/actions/workflow/status/erdemoney/kickstarrt-vps/ci.yml?logo=githubactions&logoColor=white&label=CI)](https://github.com/erdemoney/kickstarrt-vps/actions)
[![Docs](https://img.shields.io/badge/docs-wiki-blue?logo=readthedocs&logoColor=white)](https://erdemoney.github.io/kickstarrt-vps/)
[![Stack](https://img.shields.io/badge/stack-Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![TLS](https://img.shields.io/badge/tls-Let%27s%20Encrypt-2E8B57?logo=letsencrypt&logoColor=white)](https://letsencrypt.org)
[![WAF](https://img.shields.io/badge/waf-CrowdSec-brightgreen)](https://www.crowdsec.net)
[![Tooling](https://img.shields.io/badge/tooling-just-66459B)](https://just.systems)

</div>

---

kickst**Arr**t wires together everything a media library needs — **instant Usenet streaming that
keeps nothing on disk**, automatic TLS, and edge security — as code, on a VPS. Direct Traefik
`:443` ingress (Cloudflare is DNS-only — no video crosses its network), Tailscale
+ provider or UFW firewall controls, and no GPU.

## Architecture

```
Internet ----------------------------+
                                     |
Tailnet -- Tailscale ----------------+----> Traefik <----> CrowdSec
                                               |
                                               v
                                        Internal network
                                               |
                                               v
                                           Services
```

Cloudflare DNS resolves public service names to the VPS.

**The media loop:** Prowlarr finds Usenet releases → Sonarr/Radarr send them to InfiniDysk → it
fetches them from your Usenet provider and writes a tiny `.strm` link into the library → Jellyfin
streams from the provider. Zero local storage, immediately playable.

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
| `infinidysk` | Usenet streaming gateway — downloads NZBs, serves the SABnzbd API, writes `.strm` links |

## Key features

- **Nothing stored locally** — the library is made of tiny `.strm` links; media streams from your
  Usenet provider on demand
- **Automatic TLS** — Traefik issues a `*.DOMAIN` Let's Encrypt wildcard via Cloudflare
  DNS-01; services can be opted into public HTTPS with `just public enable <service>`
- **Layered security** — Tailscale private administration, provider-firewall controls where
  available or host-firewall controls otherwise,
  Traefik TLS and entrypoint isolation, CrowdSec WAF, and application logins; `just health`
  checks the deployment without changing it
- **Private admin panels** — the \*arrs, InfiniDysk and the Traefik dashboard resolve by name
  *only on your tailnet* (CoreDNS + Tailscale split DNS): `https://radarr.<DOMAIN>` from any
  tailnet device, no public records, no extra login — the tailnet is the gate
  ([Tailscale](https://erdemoney.github.io/kickstarrt-vps/tailscale))
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

After setup: configure your libraries and users in Jellyfin and Seerr ([the docs](https://erdemoney.github.io/kickstarrt-vps/)),
then optionally enable public routers, add DNS records, and open the serving ports in your chosen firewall.

Requires [Docker](https://docs.docker.com/engine/install/) and
[just](https://just.systems/man/en/installation.html) — your distro's package manager or a
[release binary](https://github.com/casey/just/releases). Both are installed by the bootstrap
script above, which also adds the invoking user to Docker's group.

## Docs

In reading order for a first deploy:

- [**Quickstart**](https://erdemoney.github.io/kickstarrt-vps/quickstart) — the ordered walkthrough: get in via Tailscale, choose the firewall, secrets, first boot, app setup, go public
- [**Tailscale**](https://erdemoney.github.io/kickstarrt-vps/tailscale) · [**Cloudflare**](https://erdemoney.github.io/kickstarrt-vps/cloudflare) — private access, DNS, and certificates
- [**Service wiring**](https://erdemoney.github.io/kickstarrt-vps/services/wiring) — app integrations
- [**Services**](https://erdemoney.github.io/kickstarrt-vps/services) · [**Providers**](https://erdemoney.github.io/kickstarrt-vps/providers) — stack-specific app notes and provider recommendations
- [**Security**](https://erdemoney.github.io/kickstarrt-vps/security) · [**Adding services**](https://erdemoney.github.io/kickstarrt-vps/services/extending) — security model and extending the stack
- [**Traefik**](https://erdemoney.github.io/kickstarrt-vps/services/traefik) — HTTPS routing and public exposure
- [**Maintenance**](https://erdemoney.github.io/kickstarrt-vps/maintenance) · [**Updates & CI**](https://erdemoney.github.io/kickstarrt-vps/maintenance/updates) — ongoing ops
- [**VPS Setup**](https://erdemoney.github.io/kickstarrt-vps/vps-setup) — Oracle Cloud walkthrough and guidance for other providers
- [**FAQ**](https://erdemoney.github.io/kickstarrt-vps/faq) — the design decisions, answered
