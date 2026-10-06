# Repository guide

## How the repo works

- `stacks/manifest.txt` defines Compose stack discovery and startup/shutdown order. Stacks use the shared external Docker network `internal`.
- Traefik binds public HTTPS on `PUBLIC_BIND` and tailnet HTTPS on `TAILNET_IP`. Service routers default to tailnet-only; `just public` opts services into the public entrypoint. DNS and firewall configuration are managed separately.
- Use the `justfile` as the operational interface. Its Python implementations are in `scripts/`, invoked as modules, with shared helpers in `scripts/common.py`.
- Tracked files under `data/` are configuration mounted into services; runtime directories are prepared by `just prepare`.

## Making changes

- Keep `main` as the production branch. Develop changes on short-lived feature or fix branches and merge them through pull requests; do not run production from a long-lived testing branch.
- Start each task from an up-to-date `main` on its own short-lived branch named
  `<type>/<short-description>` (for example, `feat/...`, `fix/...`, `docs/...`, or
  `chore/...`). Do not reuse an unrelated branch; create a task-specific branch
  before editing.
- Once a feature or fix is complete and its relevant local checks pass, open a pull request from its feature branch targeting `main`.
- Before opening a pull request, confirm its head branch is task-specific, its
  base is `main`, and `git log origin/main..HEAD` plus
  `git diff origin/main...HEAD` contain only the intended task. If not, create a
  fresh branch from the latest `main` and transfer only the relevant changes.
- Before merging, run the relevant local checks and ensure pull-request CI passes. Use a separate staging host or isolated environment for risky changes, with separate configuration, secrets, and persistent data.
- Deploy production from `main` using `just maintenance-run` (or the scheduled maintenance job), then verify with `just health` and relevant service logs. Revert a problematic change through Git and redeploy; deployment does not automatically roll back.
- When adding or removing a stack, update `stacks/manifest.txt`; recipes discover stacks from that manifest.
- Keep service behavior, Compose configuration, and relevant `docs/` pages aligned. `docs/` is the operational reference for deployment and service-specific behavior.
- Preserve existing Compose and Python conventions. Administration scripts should report actionable failures via `ScriptError`; use dry-run modes where available for changes with external effects.
- Treat changes as greenfield; do not add migration, fallback, or compatibility support for prior project behavior unless explicitly requested.

## Checks

- Run `just validate` after Compose or stack changes.
- Run `pre-commit run --all-files` for repository-wide formatting and lint checks.
