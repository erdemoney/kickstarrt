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
                      Internet                           Tailscale
                          |                                 |
                          v                                 v
          Cloudflare DNS (grey-cloud A records          tailnet IP :443
          + DNS-01 certs; no video traffic)             (100.x.y.z = TAILNET_IP)
                          |                                 |
                          v                                 v
             VPS public IP :443                          Traefik https-tailnet
             (ufw: 443 opened last;                      (panels + dashboard:
              :80 = https-redirect only,                  radarr sonarr prowlarr bazarr
              :22 = tailnet only)                         decypharr; tailnet-only, always on)
                          |                                 |
                          v                                 |
      Traefik https  ----> CrowdSec (WAF/blocking) -----------+
      (PUBLIC_BIND:443)
                          |
                          v
              Docker "internal" network
              +-----------------------------+
              | jellyfin     seerr          |   jellyfin + seerr also served on the tailnet
              | radarr       sonarr         |
              | prowlarr     bazarr         |   everything else (panels, dashboard):
              | recyclarr    decypharr      |   https-tailnet only
              | comet        comet-postgres |   comet: admin dashboard on the tailnet + Prowlarr indexer
              +-----------------------------+
```

Media flow: Prowlarr finds releases (incl. the Torrentio debrid indexer) → Sonarr/Radarr grab
them → Decypharr resolves them into instant files on a FUSE mount → the \*arrs symlink them
into the library → Jellyfin streams to any client; Seerr handles user requests.

## The access model

The one fact to hold onto throughout setup, stated once here: when public access is enabled, the
box answers the public internet from **exactly one serving port — `443` (Traefik)**, plus `80`
as a pure `http → https` redirect, and both are opened deliberately as the
[last setup step](quickstart#12-go-public-last). **The DNS resolver and all admin panels are
tailnet-only**; SSH follows the firewall policy you chose, reached by name via [Tailnet DNS](tailnet).
The whole setup runs inside that private window — the reasoning behind these choices is
collected in the [FAQ](faq).

**HTTPS comes out of the box.** Traefik's ACME provider issues a **Let's Encrypt wildcard
certificate for `*.DOMAIN`** via the Cloudflare DNS-01 challenge (`CLOUDFLARE_DNS_TOKEN`),
renewed automatically. Every service's UI is available on the tailnet immediately; opt a service
into public routing with `just public enable <service>`, then add its [A record](ingress) and open
the firewall separately. No per-app TLS configuration is involved.

## VPS sizing

A streaming-only setup like this doesn't need much. **2 vCPU / 4 GB RAM** handles a small
house; **4 vCPU / 8 GB** is comfortable if Jellyfin has to transcode to clients. The stack
streams from debrid and never stores a media library on the host, so disk is just the OS +
config — 10–20 GB is plenty (container images plus a bit of headroom).

There is **no GPU passthrough here** — VPS hosts are CPU-only, so Jellyfin transcodes in
software. Keep your library direct-play friendly (same codec/container as your clients) and
you'll rarely transcode at all ([FAQ](faq#why-does-jellyfin-transcode-in-software-no-gpu)).

## Operating system

**Debian** (stable) is the safe default — minimal, long support cycles, and every Docker
guide assumes it. Most providers offer a Debian 12 image out of the box; Oracle Cloud
doesn't, so use **Ubuntu 26.04 Minimal** there instead. The full Oracle walkthrough is the
[OCI appendix](oci).

## Repository layout

```text
stacks/                  compose files (one folder per stack) + .env per stack
  traefik/               edge router on :443, CrowdSec container, CoreDNS, plugin + ACME
  media-server/          jellyfin, seerr, radarr, sonarr, prowlarr,
                         recyclarr, bazarr, decypharr, comet (+ comet-postgres)
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

| Page                         | What it covers                                                        |
| ---------------------------- | --------------------------------------------------------------------- |
| [Quickstart](quickstart)     | the ordered walkthrough: get in via Tailscale, choose the firewall, init, first boot, app setup, go public |
| [Tailnet DNS](tailnet)       | admin panels by name over the tailnet: CoreDNS + split DNS mechanics |
| [Decypharr](decypharr)       | debrid gateway: wizard, mounts, its side of the arr wiring            |
| [The \*arrs](arrs)           | app wiring: internal DNS names, API keys, streaming integrations, mounts; the Recyclarr-synced quality profiles |
| [Jellyfin](jellyfin)         | playback setup: libraries on the Decypharr mount, no-video-transcode policy |
| [Seerr](seerr)               | user requests and Jellyfin/Radarr/Sonarr integration                 |
| [User guide](user-guide)     | simple Jellyfin and Seerr instructions for end users                 |
| [Indexers](indexers)         | Prowlarr, debrid indexers, and AltHub for TorBox Usenet streaming    |
| [Additional services](additional-services) | how to extend the stack safely with more containers |
| [Security](security)         | layered security model: Tailscale, UFW, Docker forwarding, Traefik, and CrowdSec |
| [Ingress](ingress)           | direct `:443`: the security gate, DNS records, certificates, dashboard |
| [Services](services)         | recommended debrid and Usenet streaming providers                    |
| [Updates](updates)           | Renovate PR pipeline + CI checks end to end                           |
| [Maintenance](maintenance)   | ops recipes, backups, troubleshooting                                 |
| [FAQ](faq)                   | the design decisions, answered                                        |
| [Oracle Cloud (free tier)](oci) | appendix: free VPS from zero to a running box                        |

All app config lives under the repo's own `data/` dir — `just init` writes the stack `.env`s
and `just prepare` creates each app's runtime subdirectory there. Media is served from
the debrid FUSE mount, so there is no local media directory to configure.

For managing Radarr/Sonarr from your phone, see [Ruddarr](arrs#managing-from-your-phone).

## External references

- Decypharr docs: <https://decypharr.com/guides>
- Torrentio indexer definition: <https://github.com/dreulavelle/Prowlarr-Indexers>
- Servarr wiki (Prowlarr quick start): <https://wiki.servarr.com/prowlarr/quick-start-guide>
- CrowdSec documentation: <https://docs.crowdsec.net>
