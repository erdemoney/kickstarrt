---
title: CoreDNS
parent: Services
nav_order: 13
---

# CoreDNS

CoreDNS is the small DNS resolver in the `traefik` stack. Tailscale split DNS sends lookups for
`DOMAIN` to this resolver, which answers the apex and every name below it with the VPS's tailnet
IP. This lets tailnet devices open services at `https://<service>.<DOMAIN>`; it does not publish
public DNS records. See [Tailscale](../tailscale) for client-side setup.

The tracked Corefile is `data/coredns/Corefile`. The container substitutes `DOMAIN` and
`TAILNET_IP` from its environment and binds DNS to `TAILNET_IP:53` only. `just init` sets the
tailnet address, and `just health` checks the generated Corefile and container state.

To verify from a tailnet device, resolve any service name, for example `radarr.<DOMAIN>`; it should
return the server's tailnet IP. The stack's split-DNS suffix is dedicated to this setup, since all
names under it resolve to the same IP. DNS lookups fail until the resolver is running after first
boot.

If resolution fails, confirm CoreDNS is running with:

```bash
docker compose -f stacks/traefik/compose.yaml ps coredns
just health
```

In UFW mode, DNS port `53` must be allowed from the tailnet and Docker-forwarded traffic must pass
through the configured `ufw-docker` gate. Provider-firewall mode relies on the provider's inbound
rules.

## Further reading

- [CoreDNS documentation](https://coredns.io/manual/toc/)
