---
title: Other providers
parent: VPS Setup
nav_order: 2
---

# Other VPS providers

The stack is not tied to a specific host. Choose a VPS with at least **2 vCPU and 4 GB RAM**, a
Debian 12 or Ubuntu LTS image, and a public IPv4 address. A reserved or static IP is preferable so
DNS records remain stable. Confirm that the provider supports the container architectures used by
the stack.

Before deploying, check that you have:

- SSH key-based access and a provider console or other recovery route.
- A configurable provider firewall, or permission to manage the host firewall with UFW.
- Outbound internet access for pulling images and reaching your Usenet provider.
- A way to open inbound ports `80` and `443` only when you deliberately publish services.

If the provider maps a public address to a private VPS address, Traefik binds to the local address
while Cloudflare records use the public address; the [Quickstart](../quickstart) explains the
`PUBLIC_BIND` setting.

Follow the common [Quickstart](../quickstart) for bootstrap, firewall selection, and deployment.
For Cloudflare DNS records and certificate tokens, see [Cloudflare](../cloudflare). The
[Oracle Cloud guide](oracle-cloud) shows one provider-specific setup and recovery flow.
