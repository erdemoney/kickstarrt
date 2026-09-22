---
title: Ingress
nav_order: 13
---

# Ingress: Traefik on :443

Public traffic path: **Cloudflare DNS (DNS-only) → VPS public IP `:443` → Traefik → service on
`internal`**. Traefik routes purely by its own `Host()` labels. Cloudflare is used for exactly
two things — DNS records and the DNS-01 challenge that issues the wildcard cert — and neither
carries video (why not proxy through their edge: the [FAQ](faq#why-cant-i-proxy-media-through-cloudflare)).
There is no Cloudflare Tunnel; the box serves its own static public IP.

The VPS serves the internet from exactly one port: **TCP `443` (Traefik)**. `80` exists only
to bounce `http://` to `https://` — the entrypoint-level redirect in
`traefik.yml`, with nothing served on it — and the HSTS header (`secHeaders@file`,
sent on every https response) makes repeat browsers skip `:80` after their first visit. sshd
answers only from the tailnet ([Quickstart §6](quickstart#6-choose-the-firewall-model)).
Everything on `:443` is fronted by CrowdSec ([Security](security)).

## The security gate

The going-public actions live in the walkthrough ([Quickstart §12](quickstart#12-go-public-last));
the rule they enforce:

1. **Set up every app first over the tailnet** — the panels resolve by name there from first
   boot ([Tailnet DNS](tailnet)), and that's where the [app wiring](arrs) happens.
2. **Minimum before exposing each app: its setup is finished** — an admin account exists and
   auth is on: Jellyfin (admin on first login), Sonarr/Radarr/Prowlarr/Bazarr
   (Settings → General → Authentication), Seerr (admin on first login), Decypharr (wizard
   completed). An app that goes public before its login exists is claimable by anyone.
3. **Only then open the door** — enable the public router for each selected service with
   `just public enable <service>`, add its A record, then open `443/tcp` and `80/tcp` in either
   the selected firewall: the provider firewall in provider-firewall mode, or UFW in UFW mode.
   In UFW mode, use `sudo ufw allow 443/tcp` and
   `sudo ufw allow 80/tcp`; revoke them with `sudo ufw delete allow 443/tcp` and
   `sudo ufw delete allow 80/tcp`. These commands open Docker-published ports too when the
   [ufw-docker](https://github.com/chaifeng/ufw-docker) gate routes forwarded traffic through UFW.

One honest caveat: public traffic and tailnet traffic arrive on **different sockets**, not
different hostnames. Traefik's two https entrypoints are published on separate IPs by
`stacks/traefik/compose.yaml`: `PUBLIC_BIND` (the provider-mapped IP) reaches the `https`
entrypoint, and `TAILNET_IP` (the box's tailnet address) reaches the `https-tailnet`
entrypoint (`traefik.yml`). `jellyfin` and `seerr` default to the `https-tailnet` entrypoint
and can be opted into the public entrypoint with `just public enable <service>`, while every
panel and the dashboard use only `https-tailnet`. Nothing listens on
`0.0.0.0:80/443`, so off-tailnet peers cannot even reach a panel socket: a panel `Host:`
header sent at the public IP lands on an entrypoint with **no router for it** (404), and any
other host IP refuses the connection. No per-router IP allow-list exists to attach or forget;
being on the tailnet is the requirement to reach the panels ([Tailnet DNS](tailnet)).

## Adding a public hostname (DNS record)

Public exposure requires three separate choices: a Traefik public router, a Cloudflare **A record**,
and open firewall ports. `just public enable <service>` controls only the router; the provider
firewall or UFW controls the network path. Keeping these separate makes the public state explicit
and reversible.

1. [DNS → Records](https://dash.cloudflare.com/?to=/:account/dns) → **Add record**.
2. **Type `A`**, **Name** the subdomain (e.g. `jellyfin`, `seerr`), **IPv4 address** = the
   VPS's public IP.
3. **Proxy status: DNS only** (grey cloud). Never orange-cloud a media hostname —
   [why](faq#why-cant-i-proxy-media-through-cloudflare).
4. Save; DNS propagates in minutes.

**Keep the public surface minimal.** The only hostnames anyone needs are
`seerr.<DOMAIN>` (so they can request) and `jellyfin.<DOMAIN>` (so they can watch). Nothing
else gets an A record — the admin panels stay off the public DNS and are reached over the
tailnet by name ([Tailnet DNS](tailnet)).

## Certificates

One-time setup, then automatic. Traefik's ACME provider creates the `_acme-challenge` TXT
record via the Cloudflare API (`CLOUDFLARE_DNS_TOKEN`, created in the
[Quickstart](quickstart#5-configure-the-stack)) and issues a **Let's Encrypt
wildcard cert for `*.DOMAIN`** — one cert covering every hostname that terminates at Traefik,
public or tailnet. Because it's the **DNS-01** challenge, certs issue before any DNS record
or app exists, and no inbound ports are required. Renewals and per-app HTTPS are automatic
(`tls=true` on every router). Confirm issuance in the Traefik dashboard's ACME panel.

There is **no Let's Encrypt account to create** —
[why](faq#why-is-there-no-lets-encrypt-account-to-create). Traefik registers an account without
contact information. While experimenting, use the **staging CA** — Let's Encrypt rate limits
"last up to one week and cannot be overridden":

```yaml
caServer: https://acme-staging-v02.api.letsencrypt.org/directory   # in data/traefik/traefik.yml
```

then `just up`. Staging certs are untrusted (browsers warn — expected); switching back to
production means dropping the account storage first so the staging account isn't reused:

```bash
just down && rm -f data/traefik/acme.json && just up   # dirs re-creates it 0600
```

### Editing Traefik's config

Traefik's static config is tracked at `data/traefik/traefik.yml` and mounted directly by
Compose. **Edit this file.** It is not generated or overwritten by `just up`. The
entrypoint bind IPs (`PUBLIC_BIND` / `TAILNET_IP`) are published from
`stacks/traefik/compose.yaml`'s ports instead of the static config — see that file's port comment.
`dynamic.yml` and `data/crowdsec/acquis.yaml` need no rendering and are mounted as tracked files
(`dynamic.yml` resolves its one secret at runtime with Traefik's Go templating).

## Traefik dashboard

`https://traefik.<DOMAIN>`, behind basic auth (`TRAEFIK_DASHBOARD_CREDENTIALS`). Its router
sits on the `https-tailnet` entrypoint, so it is served only to the tailnet IP like the
panels (see [the security gate](#the-security-gate)); the loopback of an SSH port-forward is
deliberately not covered — get on the tailnet first ([Quickstart §3](quickstart#3-verify-ssh-over-the-tailnet)).
For any \*arr-scale question — "is the cert issued?", "which routers exist?" — it's the
fastest place to look. Reach it over the tailnet at `https://traefik.<DOMAIN>`.
