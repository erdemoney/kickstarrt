---
title: Updates & CI
parent: Maintenance
nav_order: 3
---

# Updates & CI

This page covers the automation that runs against the repo on GitHub: a **CI gate** that rejects
bad pushes/PRs, and a **Renovate pipeline** that opens version-bump PRs. The two are the server-
side mirror of the local pre-commit workflow.

## CI checks

`.github/workflows/ci.yml` runs on every push to `main`, every pull request, and manual
dispatches:

| Job        | Check                                         | Fails on                                         |
| ---------- | --------------------------------------------- | ------------------------------------------------ |
| `lint`     | `check-yaml` (pre-commit)                     | malformed YAML (unsafe tags allowed)             |
| `lint`     | `check-json` (pre-commit)                     | malformed JSON                                   |
| `lint`     | `docker compose config -q` per stack          | a compose file that doesn't parse                |
| `gitleaks` | `gitleaks/gitleaks-action` (`fetch-depth: 0`) | a secret / API key committed anywhere in history |

The checks reuse the exact hooks from `.pre-commit-config.yaml`, so what's enforced locally is
also enforced on GitHub. Secrets can't sneak past a push: a leaked key fails CI even if it's been
removed in a later commit.

## Renovate pipeline

[Renovate](https://ghcr.io/renovatebot/renovate) runs self-hosted in a GitHub Actions workflow
and opens pull requests for pinned container images, GitHub Actions, pre-commit hooks, and the
Restic image in `justfile`. Review and merge the PR, then the server can pull and re-create the
containers during its scheduled maintenance window.

## How it works

- `.github/workflows/renovate.yml` runs daily at `06:00 UTC` (and on manual
  `workflow_dispatch`).
- `.github/renovate.json` is the config. The name is Renovate's auto-discovered repo-config
  location, which is what keeps the repository **onboarded**. The workflow also supplies the
  current repository through `RENOVATE_REPOSITORIES`, so the same configuration works in the
  upstream repository and in private forks. It enables the `docker-compose`, `github-actions`,
  and `pre-commit` managers, plus a custom manager for the Restic and hunt images in `justfile`.
- Do **not** rename that file. Renovate treats an auto-discovered config as proof the repository is
  onboarded; with no config at a default path and no onboarding PR, it skips the repository as
  `disabled-no-config` and exits 0 — a green run that silently does nothing, with no PRs and no
  dependency dashboard issue.
- Docker-image minor/patch bumps are grouped into a media-stack PR; Docker major bumps are split
  out by dependency (`separateMultipleMajor`). GitHub Actions updates are grouped separately from
  image updates, with major and non-major updates kept separate.
- Renovate creates PRs as soon as it can push the update branch. There is no dashboard approval
  step; GitHub's configured token permissions still apply. The default PR rate limit is two new
  PRs per hour.
- `automerge: false` — nothing merges without you.
- A **dependency dashboard** issue tracks managed dependencies and updates blocked by scheduling,
  rate limits, or approval requirements. Its checkboxes can force eligible updates to run early.
- Pins are preserved: bumps go `:v3.4.1` → `:v3.5.0`, never `:latest`.

## Prerequisites (one time)

1. Repo hosted on GitHub (it is).
2. A **Personal Access Token** with write access, stored as the `RENOVATE_TOKEN` Actions secret:
   - Create at <https://github.com/settings/tokens>.
   - Classic: scopes `repo` and `workflow` (`repo` allows branch pushes; `workflow` allows
     GitHub Actions dependency updates to change files under `.github/workflows/`).
   - Fine-grained: `Contents`, `Pull requests`, and `Issues` **read and write**, plus `Workflows`
     **write** so Renovate can update `.github/workflows/`; restrict the token to this repo.
3. Store it once as a repo **Actions secret**. From the repository root:

   ```bash
   gh secret set RENOVATE_TOKEN
   ```

   The command prompts securely for the token. Alternatively use GitHub → repo **Settings →
   Secrets and variables → Actions → New repository secret**.

A GitHub App install is _not_ needed — this is the self-hosted action setup.

## GitHub repository setup

Run these commands once after forking. They are safe to run again if a workflow is already
enabled. Run them from the repository root: every `gh` command below infers the repository from
the checkout's remote, so no `--repo` flag is needed. `REPO` exists only for the `gh api` calls,
which take an explicit `owner/repo` path.

```bash
# Confirm the workflows exist, then enable them in the fork.
gh workflow list
gh workflow enable ci.yml
gh workflow enable renovate.yml
gh workflow enable pages.yml

# Configure GitHub Pages to deploy from the Pages workflow.
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
gh api --method PUT "repos/$REPO/pages" --field build_type=workflow

# Run CI and Renovate manually when verifying the setup.
gh workflow run ci.yml
gh workflow run renovate.yml
gh run list
# Follow a run until it finishes, or inspect only failed-step logs.
gh run watch
gh run view <RUN_ID> --log-failed
```

If the Pages site has never been created, use GitHub → repo **Settings → Pages**, choose
**GitHub Actions** as the source, and then rerun the `pages.yml` workflow. Verify the resulting
site with:

```bash
gh api "repos/$REPO/pages" --jq '.html_url'
```

To make CI a real merge gate, protect `main` after the first successful CI run. This enables
required pull-request reviews and both CI jobs:

```bash
gh api --method PUT "repos/$REPO/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "CI / Syntax + formatting",
      "CI / Secrets (git history)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Review the protection settings with:

```bash
gh api "repos/$REPO/branches/main/protection"
```

The branch-protection command requires repository administration permission. If the repository
uses organization rulesets instead, configure the equivalent ruleset in **Settings → Rules →
Rulesets**.

## First onboarding

1. `.github/renovate.json` + `.github/workflows/renovate.yml` already exist on `main`.
2. Set the `RENOVATE_TOKEN` secret (above).
3. Run once manually with `gh workflow run renovate.yml`, or use GitHub → Actions
   → **Renovate** → _Run workflow_, or wait for the cron.
   The first run opens PRs for any outdated tags. If every image is already current there are
   simply no PRs yet — the first ones appear when a newer tag is published. (No "onboarding"
   PR, because the config is already on the default branch at an auto-discovered path.)

## Day-to-day flow

```
# 1. On GitHub: review + merge the Renovate PR
# 2. The server's overnight timer runs automatically:
just maintenance-run   # equivalent manual operation
```

Enable the timer once on the server with:

```
just maintenance-schedule             # daily at 03:00 local time
just maintenance-schedule "*-*-* 04:30:00"
```

The job uses `git pull --ff-only`, so local edits or a non-fast-forward branch stop the deployment
rather than being merged or overwritten. It updates Compose services and verifies Docker plus every
expected container; see
[Maintenance](../maintenance#scheduled-maintenance) for logs and failure handling.

Minor/patch PRs are safe to apply whenever (pinned tags, images pulled on demand). Major-bump
PRs deserve reading the release notes first.

## Troubleshooting

- **No PRs?** Check the Renovate run under Actions — its log states exactly what it saw
  (e.g. `Dependency extraction complete ... depCount`).
- **Push rejected for a GitHub Actions update**: the `RENOVATE_TOKEN` also needs `Workflows: write`
  (fine-grained) or the `workflow` scope (classic), in addition to branch-push access.
- **`Write access to repository not granted`** at push time: token needs `Contents: read and
  write` (fine-grained) or `repo` (classic), allowed on this repository.
- **Token expired/wrong**: re-set `RENOVATE_TOKEN` (`gh secret set RENOVATE_TOKEN` from the
  repository root, or Settings → Secrets and variables → Actions), then re-run via
  `workflow_dispatch`.
- **Validate config locally before pushing**:

  ```bash
  docker run --rm -v "$PWD":/repo ghcr.io/renovatebot/renovate:latest \
      renovate-config-validator /repo/.github/renovate.json
  ```
