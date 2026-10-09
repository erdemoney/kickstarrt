---
title: Service wiring
nav_order: 6
---

# Service wiring: automated integrations and internal addresses

First-run setup happens over the tailnet while nothing is public
([Quickstart §9](../quickstart#9-set-up-the-apps)). After creating InfiniDysk's admin account and
the Arr/Prowlarr/Bazarr first-run accounts, run `just wire --dry-run` to preview cross-service
changes, then `just wire` to review and confirm them. App-specific setup choices are covered on the
[service pages](../services).

## Automated wiring

`just wire` reconciles repeatable integrations through the apps' APIs. It configures Arr root
folders and InfiniDysk download clients/registrations, sets Radarr's profile language to **Original**
per the [TRaSH Guide](https://trash-guides.info/Radarr/radarr-setup-quality-profiles/), enables
**Skip Free Space Check** in Sonarr and Radarr for InfiniDysk link imports, links Prowlarr and Bazarr
to the Arrs, provisions Recyclarr secrets and its initial sync, and sets up import scans from
Sonarr/Radarr to Jellyfin. Recyclarr manages the profiles, naming, and Propers/Repacks scoring. The
script also bootstraps a fresh Jellyfin and Seerr, configures Seerr's Jellyfin and Arr connections,
and adds Maintainerr's Jellyfin, Seerr, Radarr, and Sonarr connections. Cleanup rules and retention
actions remain operator-configured in Maintainerr.

The default mode is interactive: planned changes are displayed with secrets redacted and confirmed
one checkpoint at a time. The command stops after a declined or failed checkpoint. Use `--yes` for
non-interactive runs after reviewing the dry run:

```bash
just wire --dry-run   # preview planned changes
just wire             # review and confirm changes
just wire --yes       # non-interactive after reviewing the dry run
```

It reads app configuration to obtain the existing API credentials, writes Recyclarr's managed
`secrets.yml`, and makes API requests from a temporary helper container on `internal`. Maintainerr
stores connected-service keys in its SQLite database under `data/maintainerr`; its API has no
authentication, so these requests stay on the internal network. The InfiniDysk admin account,
indexer choices, subtitle providers, language profiles, and Maintainerr cleanup rules remain GUI
steps; see [InfiniDysk](infinidysk), [Prowlarr](prowlarr), [Bazarr](bazarr), and
[Maintainerr](maintainerr).

If Jellyfin's first-run wizard is already complete but there is no valid API key, `just wire` prompts
for the existing admin credentials to create one. `--yes` cannot prompt; create a key in Dashboard →
API Keys or run `just wire` interactively.

## Internal URLs and API keys

Containers share the `internal` network and reach each other by service name. When an app asks for
another app's URL and API key, use the internal URL below—not `localhost` or a public hostname.
Public hostnames are for browsers.

| Service | Internal URL | Port | API key location |
| --- | --- | --- | --- |
| Jellyfin | `http://jellyfin:8096` | 8096 | Dashboard → API Keys; created/reused by `just wire` |
| Seerr | `http://seerr:5055` | 5055 | Auto-generated `main.apiKey` in `data/seerr/config/settings.json` |
| Maintainerr | `http://maintainerr:6246` | 6246 | Connected-service API keys are stored in Maintainerr's SQLite database under `data/maintainerr` |
| Radarr | `http://radarr:7878` | 7878 | Settings → General → API Key |
| Sonarr | `http://sonarr:8989` | 8989 | Settings → General → API Key |
| Prowlarr | `http://prowlarr:9696` | 9696 | Settings → General → API Key |
| Recyclarr | — | — | Managed automatically; nothing to paste |
| Bazarr | `http://bazarr:6767` | 6767 | Outbound only |
| InfiniDysk | `http://infinidysk:3000` | 3000 | Generated `INFINIDYSK_API_KEY` in `stacks/media-server/.env` |

Check connectivity from inside a container with, for example,
`docker exec <service> curl -fsS http://sonarr:8989/ping`.
