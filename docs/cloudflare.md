---
title: Cloudflare
nav_order: 5
---

# Cloudflare: DNS and certificates

This stack uses Cloudflare for authoritative DNS and Traefik's DNS-01 certificate challenge.
Public service records must be **DNS only** (grey cloud), so video traffic goes directly to the
VPS rather than through Cloudflare's proxy. See the [FAQ](faq#why-cant-i-proxy-media-through-cloudflare)
for the reason.

## Prepare the domain

Add your domain to Cloudflare and use Cloudflare's assigned nameservers at your registrar. Keep the
domain in this account; the API token below is scoped to this zone and is used by Traefik for
certificate challenges.

## API token for certificates

Traefik uses a Cloudflare API token to create and remove the `_acme-challenge` TXT record for the
Let's Encrypt wildcard certificate. Create a custom token in
[Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) with:

- **Zone → Zone → Read**
- **Zone → DNS → Edit**
- **Zone Resources → Include → Specific zone** → select your domain

Enter the token as `CLOUDFLARE_DNS_TOKEN` during `just init`; init verifies it. It can be entered
later if skipped. See [Traefik certificates](services/traefik#certificates) for issuance and
renewal behavior.

## Public DNS records

After enabling a service's public Traefik router, add a DNS record for its hostname:

1. Open [Cloudflare DNS → Records](https://dash.cloudflare.com/?to=/:account/dns) and choose **Add record**.
2. Set **Type** to `A`, **Name** to the service subdomain (for example `jellyfin` or `seerr`), and
   **IPv4 address** to the VPS's public IP.
3. Set **Proxy status** to **DNS only** (grey cloud), then save.

Use a stable or reserved public IP so the record remains valid after restarts or rebuilds. DNS
records do not enable a router or open firewall ports; follow [Traefik's public access procedure](services/traefik#public-access)
for the complete sequence. Keep admin panels off public DNS; they resolve over Tailscale
([Tailscale](tailscale)).

## DNS-only media traffic

Do not orange-cloud media hostnames. Cloudflare's proxy is not used for this stack's video traffic;
records point directly to the VPS. Cloudflare DNS remains involved in certificate challenges, but
does not carry the media stream.
