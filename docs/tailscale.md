---
title: Tailscale
nav_order: 4
---

# Tailscale: private access to the stack

Tailscale provides the private network used to administer the VPS and reach its management
interfaces. SSH, the Traefik dashboard, and admin panels are restricted to the tailnet; the
public entrypoint is configured separately. The tailnet does not replace application login:
keep each app's authentication enabled.

## Connect the host and devices

The Quickstart installs and authenticates Tailscale on the host before closing public SSH access.
Use the same tailnet on the devices that administer the stack. Verify connectivity with
`tailscale status` on the host and confirm SSH works from a tailnet device before changing the
firewall ([Quickstart](quickstart#2-get-in-join-the-tailnet)).

MagicDNS provides each tailnet device with its Tailscale name. This stack also uses split DNS so
service names under `DOMAIN` resolve to the VPS's tailnet IP. The split nameserver is registered
in the Tailscale DNS console during setup; `just dns` prints the resolver details. The resolver
implementation and verification steps are in [CoreDNS](services/coredns).

## Service access

From a tailnet device, open services at `https://<service>.<DOMAIN>`. Traefik accepts management
traffic only on its tailnet-bound HTTPS entrypoint; the admin services have no public DNS records
([Traefik](services/traefik)). Public access, when enabled, is a separate opt-in for selected
services.

Keep `DOMAIN` dedicated to this stack while it is registered as a split-DNS suffix: CoreDNS answers
all names under it with the VPS's tailnet IP. Until CoreDNS is running, lookups for those names
will fail; this is expected between the Tailscale DNS setup step and the first stack boot.

If the VPS is rebuilt or its tailnet IP changes, update the nameserver IP in the
[Tailscale DNS admin console](https://login.tailscale.com/admin/dns) after `just init` updates
`TAILNET_IP`. For local DNS cache issues, reconnect the client to the tailnet or flush its DNS
cache. `just health` checks the host-side resolver and container state.

For Tailscale ACLs, client setup, and account administration, see the
[official Tailscale documentation](https://tailscale.com/kb/).
