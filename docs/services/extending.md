---
title: Adding services
nav_order: 22
---

# Adding services

The core stack is intentionally small. You can extend it, but treat every additional container
as part of the security and backup boundary: give it only the network access, host paths, and
public exposure it actually needs.

## Choose a home

For a service that belongs with the media apps, add it to
`stacks/media-server/compose.yaml`. It already joins the external `internal` network and is
included by `just up`, `just validate`, and the CI Compose check.

For a separate concern, create another stack under `stacks/<name>/compose.yaml`, then add the
stack name to `stacks/manifest.txt`. The lifecycle commands, health checks, and CI Compose check
read that manifest automatically.
Use the same external network declaration:

```yaml
networks:
  default:
    name: internal
    external: true
```

Run `just networks` before the first start. Containers on `internal` reach one another by
service name, for example `http://sonarr:8989`; they should not use public hostnames or
`localhost` for app-to-app traffic.

## Service checklist

1. Pin the image to a version that supports the VPS architecture and avoid `latest`.
2. Add `restart: unless-stopped` and `no-new-privileges:true` unless the service has a documented
   reason not to use them.
3. Give persistent state its own `data/<service>` directory and add that directory to the
   backup scope. Do not bind-mount the repository source tree.
4. Run the container with `ENV_PUID`/`ENV_PGID` where the image supports them, and document any
   ownership or elevated capability requirement.
5. Mount the host's time zone read-only (`/etc/localtime:/etc/localtime:ro`) so schedules and log
   timestamps follow the VPS's local time, like the rest of the stack
   ([Quickstart → Set the box's time zone](../quickstart#set-the-boxs-time-zone)).
6. Add a healthcheck when the image exposes a reliable local endpoint or command.
7. Keep the service on the internal network unless another container needs to reach it.
8. Expose it through Traefik only when necessary. Admin services should use the
   `https-tailnet` entrypoint; public services need a deliberate security review, authentication,
   and an entry in the public-hostname procedure. For the built-in services, use
   `just public enable <service>` rather than editing Compose labels.
9. Add its configuration and operational notes to the appropriate docs page.
10. Run `just validate`, `just update <service>`, and `just health` before using it.

## Services worth considering

### Homarr

Homarr is a lightweight dashboard. Add it to the media stack with a persistent
`data/homarr` directory and a tailnet-only Traefik router. Point its widgets at internal
URLs such as `http://sonarr:8989`, `http://radarr:7878`, and `http://jellyfin:8096`.

## Validate the extension

```bash
just validate
just update <service>
just health
```

Do not open a new public port as a shortcut. Add a Traefik route, keep the service on the correct
entrypoint, and update the security documentation first.
