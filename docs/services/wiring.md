---
title: Service wiring
nav_order: 6
---

# Service wiring: networking and app integrations

First-run setup happens over the tailnet while nothing is public
([Quickstart §9](../quickstart#9-set-up-the-apps)) — open `https://radarr.<DOMAIN>` and friends
from any tailnet device. Run `just wire --dry-run` first to preview the repeatable changes,
then run `just wire` to review and confirm each checkpoint. The remaining GUI steps are
documented below.

## Automated wiring

After the first-run admin accounts and the InfiniDysk admin account exist, `just wire` can
reconcile the repeatable cross-service links through the applications' REST APIs — including
Seerr's own first-login wizard, which it completes through the Jellyfin login. It does
not edit `config.xml`, `config.json`, `seerr/config/settings.json`, or InfiniDysk's own
database; those are read only to bootstrap API credentials. Requests run from inside the
containers, so the internal service names remain private.

The default mode is interactive. It discovers the current configuration, displays each
service-level change with secrets redacted, and asks for confirmation before applying it.
It stops after a declined or failed checkpoint rather than cascading through a partial setup.

```bash
just wire --dry-run   # discover and display planned changes
just wire             # review and confirm each checkpoint
just wire --yes       # non-interactive use after reviewing the dry run
```

The command handles Arr root folders, the **Download Client** entries that Sonarr/Radarr use to
reach InfiniDysk and the matching **Arr registrations** in InfiniDysk (health polling and queue
rules), Prowlarr's Sonarr/Radarr application links, Bazarr's Sonarr/Radarr
connections, Recyclarr's native secret file plus initial sync, and the Sonarr/Radarr → **Jellyfin**
connections that push a library scan on import — no more manual "Scan All Libraries" in Jellyfin.
On a fresh Jellyfin install, `just wire` also creates the admin account and a `Kickstarrt` API key
through the first-run wizard API; a fresh **Seerr** is bootstrapped the same way through the
Jellyfin login, then its **Jellyfin + Radarr + Sonarr** connections are created (media server
type, every Jellyfin library enabled for requests, and both media managers pinned to the shipped
**Direct Play** profile) using the credentials already gathered in the run, so only one prompt.
If the Jellyfin wizard is already complete and no key is in use, it
prompts for the existing admin credentials to mint one; `--yes` cannot prompt, so it errors and
skips those connections (run `just wire` in a terminal to provision the key, or generate one in
Dashboard → API Keys and re-run). Subtitle providers, language profiles, and indexer
choices, plus the InfiniDysk admin account, remain GUI steps because they require
user-specific choices or first-run authentication.

## Docker networking

One shared, `external: true` network — `internal` — carries all app-to-app traffic, Traefik
included. It's created by `just up` (`just networks` standalone); nothing inside Docker binds
an IP you need to care about — the names are what matter. Every service sets a
`container_name` matching its name, so containers are reachable at `http://<service>:<port>`
and a newly added container is reachable from every existing app.

## Internal DNS names and API keys

All services share the `internal` network, so every container reaches the others by
**service name**. Always use these internal URLs when one app asks for another — never
`localhost`, never the public subdomain (public URLs hairpin out to the internet and back,
break CORS, and add latency; they are for browsers only).

| Service   | Internal URL            | Port | API key lives at                                |
| --------- | ----------------------- | ---- | ----------------------------------------------- |
| jellyfin  | `http://jellyfin:8096`  | 8096 | Dashboard → API Keys; created/reused by `just wire` |
| seerr     | `http://seerr:5055`     | 5055 | auto-generated `main.apiKey` in `data/seerr/config/settings.json` |
| radarr    | `http://radarr:7878`    | 7878 | Settings → General → API Key                    |
| sonarr    | `http://sonarr:8989`    | 8989 | Settings → General → API Key                    |
| prowlarr  | `http://prowlarr:9696`  | 9696 | Settings → General → API Key                    |
| recyclarr | —                      | —    | automatic — nothing to paste (see below)        |
| bazarr    | `http://bazarr:6767`    | 6767 | (outbound only)                                 |
| infinidysk | `http://infinidysk:3000` | 3000 | generated `FRONTEND_BACKEND_API_KEY` in `stacks/media-server/.env` |

Rule of thumb: when any UI asks for another app's **URL + API key**, use the
`http://<service>:<port>` from the table and the key from the target app. Sanity-check any
link from inside the network:
`docker exec <service> curl -fsS http://sonarr:8989/ping`.

## Root folders

Sonarr/Radarr root folders must point at paths inside their own containers. Everything the
stack serves lives under one shared bind, `/mnt/usenet`, mounted at the same absolute path in
every media container:

- Sonarr → `/mnt/usenet/library/shows`
- Radarr → `/mnt/usenet/library/movies`

`just prepare` creates and owns the whole tree to `ENV_PUID`/`ENV_PGID` (`/mnt/usenet`,
`library/`, `library/shows`, `library/movies`, `completed-downloads`), so there's nothing to run
first and no startup order to respect. By hand it is just
`mkdir -p /mnt/usenet/library/{shows,movies} /mnt/usenet/completed-downloads` on the host — no
sudo once the tree is owned by the PUID. Then **Add Root Folder** in Sonarr/Radarr; `just wire`
does it for you.

Every service that touches media — `sonarr`, `radarr`, `bazarr` (subtitles land next to the
video), `jellyfin` (playback) and `infinidysk` (staging and repair checks) — reaches the
library, the staging directory and InfiniDysk's `http://infinidysk:3000` links through that one
bind, so a path is spelled the same everywhere. Then in Jellyfin add the libraries the same way
([Jellyfin setup](jellyfin) covers libraries plus the transcode policy). Also set
Jellyfin → Playback → **Transcode path** to `/transcode` (a tmpfs — transcode scratch never hits
disk; this edition transcodes in software, so keep the library direct-play friendly).

## Imports are STRM links, not copies

There is no local download here: InfiniDysk writes a `.strm` file per item, and importing renames
it into the root folder — a few kilobytes, where the payload streams from your Usenet provider at
playback. Two consequences follow:

- **The staging directory and the root folders must be on the same filesystem.** InfiniDysk
  stages finished releases in `/mnt/usenet/completed-downloads` and the roots are
  `/mnt/usenet/library/shows` + `/mnt/usenet/library/movies`, all real dirs on the same bind, so
  the import is a rename — instant.
- **The link's URL must be reachable from the media server.** The URL is written with InfiniDysk's
  base URL, `http://infinidysk:3000`, and Jellyfin resolves that name because both sit on the
  `internal` network. A `.strm` file is a URL, not a path, so a media server that cannot reach
  that address sees an unplayable library even though the files look right.

## Prowlarr application sync

`just wire` provisions Prowlarr's Sonarr and Radarr application links and enables full sync.
Every indexer added in Prowlarr is then pushed to both apps. Choose and test indexers in Prowlarr;
there is no reason to recreate the application links by hand unless you intentionally changed them.

## Seerr → Jellyfin + Radarr + Sonarr (requests)

`just wire` reconciles the three Seerr connections ([Automated wiring](#automated-wiring)): a
fresh Seerr is completed through the Jellyfin login, then a server is created for each managed
\*arr and Jellyfin's libraries are enabled. You can still adjust any of it in the Seerr UI — a
later `just wire` only re-asserts connection fields (URL, API key, root folder, sync enabled)
and never overwrites a quality profile or anime/language choice you made.

Manual setup (fallback):

1. Seerr → Settings → **Jellyfin**: server name, URL `http://jellyfin:8096`, and an **API key
   generated on the Jellyfin server** (Dashboard → API Keys — the admin account is created on
   Jellyfin's first login).
2. Seerr → **Radarr** and **Sonarr**: enable, add `http://radarr:7878` / `http://sonarr:8989`
   + API keys, pick the shipped **Direct Play** quality profile and the root folder for each.
3. Users can now request via Seerr, which pushes to Radarr/Sonarr.
4. Under Seerr → Settings → **Jellyfin**, enable at least one library so Seerr maps requests
   to a root folder.

## Service-specific configuration

See [Bazarr](bazarr) for subtitle providers and language profiles, and [Recyclarr](recyclarr)
for the quality-profile design and synchronization workflow.
