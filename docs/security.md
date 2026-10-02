---
title: Security
nav_order: 12
---

# Security overview

This deployment keeps routine administration private and makes public access an explicit choice.
Security comes from several layers working together: network access controls, HTTPS routing,
CrowdSec at the edge, and authentication in each application.

## Private administration, selective public access

Tailscale is the private route for SSH, DNS, the Traefik dashboard, and management panels. These
services are bound to the tailnet address and have no public routers. Application logins still
matter: a tailnet connection does not replace each service's own authentication. Maintainerr has no
built-in login, so it is restricted to tailnet access and must not be published directly.

Jellyfin and Seerr can be published when needed, but their public routers are disabled by default.
Enabling a router, adding its DNS record, and opening the firewall are separate, deliberate steps.
Cloudflare provides DNS and certificate validation; public traffic goes directly to the VPS.

## What protects incoming traffic

- A provider firewall or UFW limits which network traffic can reach the host. In UFW mode,
  Docker's forwarded traffic is filtered as well.
- Traefik listens separately on the public and tailnet addresses and routes only configured
  services. It provides HTTPS using an automatically renewed wildcard certificate.
- CrowdSec analyzes Traefik access logs and blocks IPs identified as hostile. It is fail-open if
  unavailable, so it adds protection at the edge but does not replace the firewall or application
  authentication.

## Secrets and checks

Keep credentials in private, ignored configuration files and out of Git. Back up the repository
and application state with encrypted Restic backups, and use the read-only `just health` check
after setup or significant host and stack changes. It reports the status of key network,
container, and CrowdSec components.

For operational details, see [Tailscale](tailscale), [Traefik](services/traefik),
[CrowdSec](services/crowdsec), [Maintenance](maintenance), and [Backups](maintenance/backups).
