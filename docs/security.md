---
title: Security
nav_order: 12
---

# Security model

Security is layered rather than delegated to one container. The deployment keeps administration
private on the tailnet, limits which host addresses accept traffic, filters forwarded Docker
traffic, terminates TLS at Traefik, and then lets CrowdSec and each application enforce the next
layer of access control.

## Traffic paths

### Administration and private panels

Tailscale is the administration plane. SSH, CoreDNS, Traefik's dashboard, and the management
panels use the tailnet address and the `https-tailnet` entrypoint. CoreDNS answers the stack's
domain only for tailnet clients through split DNS; it does not create public records.

The tailnet is not a substitute for application authentication. Keep admin accounts enabled in
every application, and treat a tailnet device as trusted only as far as its owner and local
security justify.

### Public services

Jellyfin and Seerr are the intended public services, but their routers are tailnet-only by default.
Run `just public enable <service>` to opt a service into Traefik's public entrypoint. Public DNS
records are Cloudflare DNS-only A records; Cloudflare does not proxy media traffic. In UFW mode,
the public ports remain closed until the documented `ufw allow` commands open `80` and `443`.

## Security layers

1. **Provider firewall and recovery access** provide the initial SSH path and the break-glass
   console when the VPS product offers a configurable provider firewall. Verify that feature;
   some VPS products do not include one. Otherwise, use the host firewall and keep the provider
   console as the recovery path.
2. **Tailscale** supplies the private route for SSH, DNS, dashboards, and management panels.
3. **The chosen firewall** denies public traffic by default and permits only the access the
   operator has deliberately configured. A provider firewall filters at the provider perimeter;
   UFW filters on the host. Use UFW when no configurable provider firewall is available.
4. **In UFW mode, ufw-docker** connects UFW to Docker's `FORWARD` path through `DOCKER-USER`;
   without it, published container ports could bypass UFW's `INPUT` rules. See the
   [ufw-docker documentation](https://github.com/chaifeng/ufw-docker) for implementation details.
5. **Traefik** binds public and tailnet entrypoints to separate host addresses, issues the
   wildcard certificate through Cloudflare DNS-01, and exposes only routers configured by labels.
6. **CrowdSec** reads Traefik access logs and blocks known or detected hostile IPs at the edge.
7. **Application authentication** protects the services that are reachable after the network
   layers allow them. Configure every first-run admin account before going public.
8. **Secrets and backups** stay in private ignored files, are never committed, and are covered
   by encrypted Restic backups. CI scans the full Git history for leaked secrets.

## CrowdSec

CrowdSec runs in the `traefik` stack. Traefik's JSON access log feeds the detection engine via
`data/crowdsec/acquis.yaml`; the `crowdsecurity/traefik` and
`crowdsecurity/http-cve` collections provide the detection scenarios. The Traefik bouncer plugin
enforces decisions on both HTTPS entrypoints using `CROWDSEC_BOUNCER_API_KEY`.

CrowdSec is configured fail-open: if its LAPI is unavailable, Traefik continues serving rather
than taking down the entire edge. The firewall, private entrypoint, and application login layers
remain in force. The block cache refreshes every 60 seconds.

Tailnet and private-network clients are trusted by the configured `clientTrustedIPs` ranges.
Direct ingress means Traefik sees the actual socket peer, and forwarded headers from untrusted
sources are not accepted.

## Verification

Run the read-only health panel after setup and whenever the host or stack changes:

```bash
just health
```

It checks Tailscale, the selected host-firewall state when UFW is configured, the internal Docker
network, CoreDNS's generated Corefile, container states, and the CrowdSec bouncer command. It does
not deliberately ban an IP; that would be unsafe as a routine health check.

For operational firewall checks, see [Maintenance](maintenance). For DNS behavior, see
[Tailnet DNS](tailnet).
