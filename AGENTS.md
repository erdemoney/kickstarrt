# Repository guide

## How the repo works

- `stacks/manifest.txt` defines Compose stack discovery and startup/shutdown order. Stacks use the shared external Docker network `internal`.
- Traefik binds public HTTPS on `PUBLIC_BIND` and tailnet HTTPS on `TAILNET_IP`. Service routers default to tailnet-only; `just public` opts services into the public entrypoint. DNS and firewall configuration are managed separately.
- Use the `justfile` as the operational interface. Its Python implementations are in `scripts/`, invoked as modules, with shared helpers in `scripts/common.py`.
- Tracked files under `data/` are configuration mounted into services; runtime directories are prepared by `just prepare`.

## Making changes

- When adding or removing a stack, update `stacks/manifest.txt`; recipes discover stacks from that manifest.
- Keep service behavior, Compose configuration, and relevant `docs/` pages aligned. `docs/` is the operational reference for deployment and service-specific behavior.
- Preserve existing Compose and Python conventions. Administration scripts should report actionable failures via `ScriptError`; use dry-run modes where available for changes with external effects.
- Treat changes as greenfield; do not add migration, fallback, or compatibility support for prior project behavior unless explicitly requested.

## Checks

- Run `just validate` after Compose or stack changes.
- Run `pre-commit run --all-files` for repository-wide formatting and lint checks.
