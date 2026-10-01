---
title: Traefik
parent: Services
nav_order: 11
---

# Traefik: HTTPS routing and certificates

Traefik is the stack's HTTPS entrypoint. It routes by hostname to services on the shared `internal`
Docker network and binds its public and tailnet entrypoints to separate host IPs. Public routers
are opt-in; management services remain tailnet-only. For the complete security model, see
[Security](../security) and [Tailscale](../tailscale).

## Public access

Public traffic follows **Cloudflare DNS-only record → VPS public IP `:443` → Traefik → service**.
Cloudflare provides DNS and the DNS-01 certificate challenge; it does not proxy video. Port `80`
only redirects HTTP to HTTPS. See [Cloudflare](../cloudflare) for DNS setup and the
[FAQ](../faq#why-cant-i-proxy-media-through-cloudflare) for the DNS-only requirement.

To publish a service, complete its first-run setup and authentication, then:

1. Enable its Traefik router: `just public enable <service>`.
2. Add a DNS-only A record for `<service>.<DOMAIN>` following [Cloudflare's instructions](../cloudflare#public-dns-records).
3. Open TCP ports `443` and `80` in the selected firewall. In UFW mode:

   ```bash
   sudo ufw allow 443/tcp
   sudo ufw allow 80/tcp
   ```

These are separate controls: disabling a router does not change DNS or firewall rules. The full
sequence and rollback guidance are in [Quickstart: Go public](../quickstart#12-go-public-last).

## Certificates

Traefik's ACME provider uses the Cloudflare DNS-01 challenge and `CLOUDFLARE_DNS_TOKEN` to issue a
Let's Encrypt wildcard certificate for `*.DOMAIN`. Issuance and renewal are automatic; no public
DNS record or inbound port is needed for the challenge. Configure the token as described in
[Cloudflare](../cloudflare#api-token-for-certificates). The certificate can be checked in the
Traefik dashboard.

There is no Let's Encrypt account to create ([FAQ](../faq#why-is-there-no-lets-encrypt-account-to-create)).
For testing, the staging CA can be set in `data/traefik/traefik.yml`:

```yaml
caServer: https://acme-staging-v02.api.letsencrypt.org/directory
```

Staging certificates are untrusted. Before switching back to production, remove the staging
account storage and restart:

```bash
just down && rm -f data/traefik/acme.json && just up
```

## Configuration and dashboard

Edit tracked `data/traefik/traefik.yml` for static configuration and `data/traefik/dynamic.yml` for
dynamic configuration. Compose publishes the HTTPS entrypoints on `PUBLIC_BIND` and `TAILNET_IP`;
they are not bound to every host address. CrowdSec's bouncer plugin protects both entrypoints
([CrowdSec](crowdsec)).

The dashboard is at `https://traefik.<DOMAIN>`, protected by basic auth and available only over the
tailnet. It shows active routers, certificate status, and service health. See [Tailscale](../tailscale)
for private access and [CoreDNS](coredns) for name resolution.
