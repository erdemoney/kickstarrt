---
title: CrowdSec
parent: Services
nav_order: 12
---

# CrowdSec

CrowdSec runs alongside Traefik as the edge detection and blocking layer. Traefik's JSON access
log is collected through `data/crowdsec/acquis.yaml`; the `crowdsecurity/traefik` and
`crowdsecurity/http-cve` collections provide detection scenarios. The Traefik bouncer plugin
enforces CrowdSec decisions on both HTTPS entrypoints.

The bouncer key is `CROWDSEC_BOUNCER_API_KEY`. After changing it, recreate both CrowdSec and
Traefik, then check the bouncer with `cscli bouncers list` or `just health`.

CrowdSec is configured **fail-open**: if its Local API is unavailable, Traefik continues serving.
The firewall, tailnet-only management entrypoint, and application authentication remain in force.
The decision cache refreshes every 60 seconds. Tailnet and private-network clients are trusted by
the configured `clientTrustedIPs` ranges; direct ingress lets Traefik see the socket peer and
forwarded headers from untrusted sources are not accepted.

See [Traefik](traefik) for routing and [Security](../security) for the layered access model.

## Further reading

- [CrowdSec documentation](https://docs.crowdsec.net)
