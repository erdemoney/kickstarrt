---
title: Overview
nav_order: 1
---

# kickstArrt

A public-IP media stack run through Docker on a VPS, with a single GitHub repo as the source
of truth for compose files, configs that live in code, and all setup/ops documentation. This
It uses direct Traefik `:443` ingress (Cloudflare is DNS-only) and is designed for CPU-only VPS
hosts.

```text
           Internet                                                     Tailnet
               |                                                           |
         Cloudflare DNS                                                Tailscale
               |                                                           |
      VPS public endpoint                                        VPS tailnet endpoint
               |                                                           |
               +-----------------------------+-----------------------------+
                                             |
                                             v
                                          Traefik <----> CrowdSec
                                             |
                                             v
                                 Docker "internal" network
                              +-----------------------------+
                              | jellyfin   seerr            |
                              | radarr     sonarr           |
                              | prowlarr   bazarr           |
                              | recyclarr  infinidysk       |
                              +-----------------------------+
```

Media flow: Prowlarr finds Usenet releases → Sonarr/Radarr send them to InfiniDysk → it fetches
them from your Usenet provider and writes a tiny `.strm` link into the library → Jellyfin streams
from the provider; Seerr handles user requests.

## The access model

The one fact to hold onto throughout setup, stated once here: when public access is enabled, the
box answers the public internet from **exactly one serving port — `443` (Traefik)**, plus `80`
as a pure `http → https` redirect, and both are opened deliberately as the
[last setup step](quickstart#12-go-public-last). **The DNS resolver and all admin panels are
tailnet-only**; SSH follows the firewall policy you chose, reached by name via [Tailscale](tailscale).
The whole setup runs inside that private window — the reasoning behind these choices is
collected in the [FAQ](faq).

**HTTPS comes out of the box.** Traefik's ACME provider issues a **Let's Encrypt wildcard
certificate for `*.DOMAIN`** via the Cloudflare DNS-01 challenge (`CLOUDFLARE_DNS_TOKEN`),
renewed automatically. Every service's UI is available on the tailnet immediately; opt a service
into public routing with `just public enable <service>`, then add its [A record](cloudflare) and open
the firewall separately. No per-app TLS configuration is involved.

## VPS sizing

A streaming-only setup like this doesn't need much. **2 vCPU / 4 GB RAM** handles a small
house; **4 vCPU / 8 GB** is comfortable if Jellyfin has to transcode to clients. Nothing but
tiny `.strm` links ever lands in the library, so disk is just the OS + config — 10–20 GB is
plenty (container images plus a bit of headroom).

There is **no GPU passthrough here** — VPS hosts are CPU-only, so Jellyfin transcodes in
software. Keep your library direct-play friendly (same codec/container as your clients) and
you'll rarely transcode at all ([FAQ](faq#why-does-jellyfin-transcode-in-software-no-gpu)).

## Operating system

**Debian** (stable) is the safe default — minimal, long support cycles, and every Docker
guide assumes it. Most providers offer a Debian 12 image out of the box; Oracle Cloud
doesn't, so use **Ubuntu 26.04 Minimal** there instead. The full Oracle walkthrough is in
[VPS Setup](vps-setup/oracle-cloud).

## Repository layout

```text
stacks/                  compose files (one folder per stack) + .env per stack
  traefik/               edge router on :443, CrowdSec container, CoreDNS, plugin + ACME
  media-server/          jellyfin, seerr, radarr, sonarr, prowlarr,
                         recyclarr, bazarr, infinidysk
data/                    runtime config that lives in code
  traefik/               traefik.yml, dynamic.yml
  crowdsec/              acquis.yaml
  coredns/               Corefile
  recyclarr/             shipped Direct Play (+ Sonarr Direct Play (Anime)) quality profiles + bootstrap (synced by recyclarr)
.github/                 CI checks (workflow) + Renovate pipeline (workflow + global config)
docs/                    this wiki (GitHub Pages)
justfile                 ops recipes (just up, just update-all, ...)
```

## Page map

Read the pages in order for a first deploy; after that they're reference.

| Page | What it covers |
| --- | --- |
| [Quickstart](quickstart) | Ordered walkthrough: tailnet access, firewall, initialization, first boot, app setup, and public access. |
| [VPS Setup](vps-setup) | General provider checklist, [Oracle Cloud](vps-setup/oracle-cloud), and [other providers](vps-setup/other-providers). |
| [Tailscale](tailscale) | Private administration, tailnet access, and split DNS. |
| [Cloudflare](cloudflare) | Domain setup, DNS-only service records, and certificate API token. |
| [Service wiring](services/wiring) | `just wire`, internal app URLs and API keys, and cross-service integrations. |
| [Services](services) | Stack-specific notes and official references for each service. |
| [Providers](providers) | Recommended Usenet provider and indexer options. |
| [User guide](user-guide) | Jellyfin and Seerr instructions for end users. |
| [Adding services](services/extending) | How to extend the stack safely with more containers. |
| [Security](security) | Layered security model: Tailscale, firewall, Traefik, and CrowdSec. |
| [Maintenance](maintenance) | Day-to-day operations, [backups](maintenance/backups), [back-catalog hunting](maintenance/hunt), and [Updates & CI](maintenance/updates). |
| [FAQ](faq) | Design decisions and common questions. |

All app config lives under the repo's own `data/` dir — `just init` writes the stack `.env`s
and `just prepare` creates each app's runtime subdirectory there. Media streams from your Usenet
provider, so the library on disk is only the `.strm` links under `/mnt/usenet`.

## External references

- InfiniDysk docs: <https://www.infinidysk.com/getting-started/>
- Servarr wiki (Prowlarr quick start): <https://wiki.servarr.com/prowlarr/quick-start-guide>
- CrowdSec documentation: <https://docs.crowdsec.net>
- CoreDNS documentation: <https://coredns.io/manual/toc/>
- Tailscale documentation: <https://tailscale.com/kb/>
