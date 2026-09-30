---
title: FAQ
nav_order: 17
---

# FAQ

The design decisions behind the stack, collected out of the action path. For how-to, follow
the page each answer links to.

## Why can't I proxy media through Cloudflare?

Proxy status on a hostname must be **DNS only** (grey cloud). Cloudflare's
[Service-Specific Terms](https://www.cloudflare.com/service-specific-terms-application-services/)
say that unless you're an Enterprise customer, you must use their paid services (Stream,
Images, R2) "in order to serve video and other large files via the CDN" — and Cloudflare
reserves the right to disable or limit the CDN when it suspects otherwise. Video streamed
from your own origin through the free edge isn't covered by an exception, whether or not
caching is disabled, and a Cloudflare Tunnel routes traffic through that same edge.

So this stack moves **no video through Cloudflare's network**: public hostnames are DNS-only
A records straight to the VPS, and Cloudflare only answers recursive DNS lookups and the ACME
`_acme-challenge` TXT record. That is unreservedly compliant — and since the box has a static
public IP, there's nothing to hide anyway. Details: [Ingress](ingress).

## Why no Cloudflare Tunnel?

A tunnel's main trick is hiding the origin IP — worthless on a box that owns a static public
IP and serves DNS-only records anyway. What a tunnel would add, the box already has
equivalents for: the WAF story is [CrowdSec](security) inside Traefik, and Cloudflare Access
(SSO in front of apps) would break Jellyfin's TV and mobile clients — they authenticate with
a device token, not a browser. Serving `:443` directly keeps out one more moving part and one
more third-party hop.

## Why is there no Let's Encrypt account to create?

Let's Encrypt has no signup, dashboard, or email verification. Traefik registers an ACME
account on first start and stores it in `data/traefik/acme.json`; the cert is issued
via the **DNS-01** challenge (Traefik creates and deletes `_acme-challenge` TXT records
through Cloudflare), which is why the wildcard exists before any DNS record points at the box
and no inbound port is needed. The ACME account is registered without contact information;
Let's Encrypt no longer stores account email addresses or sends certificate expiration notices.

## Why do the admin panels have no public DNS records?

Radarr, Sonarr, Prowlarr and friends are admin tools — the only people who need them are you,
and you're on the [tailnet](tailnet), where they resolve by name with the real wildcard cert
and no extra login: **being on the tailnet is the gate**. That's one fewer public,
brute-forceable login surface per app.

Honest caveat: Traefik is reachable on the box's *public* IP (that's the point of going
public), so a determined client can connect there and send a panel's `Host:` header. It
lands on the public entrypoint, which has **no router for panels** — a 404, not the app.
Only the tailnet bind serves panels ([Ingress](ingress#the-security-gate)); every panel
also keeps its own auth layered on top.

## Why is everything closed until "going public"?

A fresh VPS is scanned within minutes of booting, and an app that's live on the internet
before its first-run setup is an app with no login — claimable by anyone. So the whole setup
runs privately over the tailnet. Public routers are opt-in with `just public enable <service>`,
and `:443` opens only when you separately open the public firewall ports, as the deliberate last step
([Quickstart §12](quickstart#12-go-public-last)).

## Why does Jellyfin transcode in software (no GPU)?

VPS hosts are CPU-only — there's no `/dev/dri` to pass through. In practice, Usenet-stored
releases arrive in client-friendly codecs and direct-play covers nearly everything (sizing guidance in
the [overview](index)); transcoding is the exception, and a 2–4 vCPU box handles it when it
happens. The stack leans into this: the shipped
[Direct Play and Direct Play (Anime) quality profiles](services/recyclarr) score
anything that would force a video transcode out of the grab candidates entirely.

## Why Usenet instead of torrents or Debrid?

Usenet fits this stack's workflow: Prowlarr finds releases, Sonarr/Radarr send them to InfiniDysk,
and InfiniDysk retrieves them from a provider and exposes them to Jellyfin as `.strm` links. This
doesn't depend on a live torrent swarm or require a torrent client and its seeding setup. It's an
architectural choice, not a claim that Usenet is always better: availability depends on the indexer,
provider retention, and article availability, and playback and seeking use provider transfer
([Providers](providers)).

Debrid adds a third-party cache or host whose available content and integrations can change under
legal or rightsholder pressure. For example, Real-Debrid confirmed content filtering in response to
legal obligations after reports of cached-torrent access errors in May 2026; it had also announced
anti-piracy measures after a notice from French film distributors in 2024
([TorrentFreak's report](https://torrentfreak.com/real-debrids-renewed-piracy-crackdown-follows-corporate-restructuring/)).
That is a concrete example of service restrictions changing availability, not a prediction that
every Debrid service will close.

There is also a difference in how users participate in torrent sharing. A normal torrent client
uploads pieces to other peers while downloading and can continue seeding afterward. Debrid users
generally consume cached torrents without seeding from their own devices, so they contribute less
directly to the swarm; what a Debrid provider seeds from its own infrastructure varies by service.

## Why Ubuntu on Oracle Cloud but Debian elsewhere?

Debian stable is the safe default — minimal, long support cycles, and most providers ship a
Debian image. Oracle's catalog doesn't offer one, so the [OCI guide](oci) uses **Ubuntu 26.04
Minimal**.

## Why does CrowdSec fail open?

If the CrowdSec LAPI is unreachable, the edge lets traffic through rather than blocking
everything — a security-agent outage shouldn't take the whole stack down. The window is
seconds (the first stream sync after Traefik boot), and the toggles live in
[Security](security).
