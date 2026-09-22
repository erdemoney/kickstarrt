---
title: Service wiring
parent: Services
nav_order: 4
---

# Service wiring: networking and app integrations

First-run setup happens over the tailnet while nothing is public
([Quickstart §9](../quickstart#9-set-up-the-apps)) — open `https://radarr.<DOMAIN>` and friends
from any tailnet device. Run `just wire --dry-run` first to preview the repeatable changes,
then run `just wire` to review and confirm each checkpoint. The remaining GUI steps are
documented below.

## Automated wiring

After the first-run admin accounts and Decypharr wizard are complete, `just wire` can
reconcile the repeatable cross-service links through the applications' REST APIs — including
Seerr's own first-login wizard, which it completes through the Jellyfin login. It does
not edit `config.xml`, `config.json`, `seerr/config/settings.json`, or Decypharr's `auth.json`;
those files are read only to bootstrap API credentials. Requests run from inside the containers,
so the internal service names remain private.

The default mode is interactive. It discovers the current configuration, displays each
service-level change with secrets redacted, and asks for confirmation before applying it.
It stops after a declined or failed checkpoint rather than cascading through a partial setup.

```bash
just wire --dry-run   # discover and display planned changes
just wire             # review and confirm each checkpoint
just wire --yes       # non-interactive use after reviewing the dry run
```

The command handles Arr root folders, the **Download Client** entries that Sonarr/Radarr use to
reach Decypharr (and that make Decypharr **auto-detect** those apps — no manual entry in
Decypharr → Settings → Arrs), Prowlarr's Sonarr/Radarr application links, the self-hosted
**Comet (Local)** indexer (its git-tracked Prowlarr Cardigann adapter is mounted in with
Prowlarr's `/config`), Bazarr's Sonarr/Radarr
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
choices, plus the Decypharr provider/mount wizard, remain GUI steps because they require
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
| decypharr | `http://decypharr:8282` | 8282 | Settings → API token (shown once after wizard)  |
| comet     | `http://comet:8000`     | 8000 | (indexer, no API key — see [Comet](comet); admin dashboard `https://comet.<DOMAIN>/admin`, password set by `just init`) |

Rule of thumb: when any UI asks for another app's **URL + API key**, use the
`http://<service>:<port>` from the table and the key from the target app. Sanity-check any
link from inside the network:
`docker exec <service> curl -fsS http://sonarr:8989/ping`.

## Root folders

Sonarr/Radarr root folders must point at paths inside their own containers. The Decypharr DFS
mount (`/mnt/decypharr`) is a **read-only virtual filesystem** — its root only ever holds
Decypharr's own entries (provider folders, virtual
folders), and creating directories under it fails with `Operation not supported`, even as root.
The library therefore lives in **plain directories on the shared bind tree**, siblings of the
mount:

- Sonarr → `/mnt/shows`
- Radarr → `/mnt/movies`

`just prepare` creates and owns the library dirs and Decypharr's staging dir (`/mnt/shows`,
`/mnt/movies`, `/mnt/downloads` — to `ENV_PUID`/`ENV_PGID`), so there's nothing to run first —
no mount-ordering, because they're ordinary dirs the *arrs can write whatever the DFS
mount state. (By hand it's just `mkdir -p /mnt/debrid/shows /mnt/debrid/movies
/mnt/debrid/downloads` on the host — no sudo once the tree is owned by the PUID.) Then
**Add Root Folder** in Sonarr/Radarr.

Every service that touches media — `sonarr`, `radarr`, `bazarr` (subtitles land next to the
video) and `jellyfin` (playback) — reaches both halves through the shared bind
`- /mnt/debrid:/mnt:rslave`: the library dirs at `/mnt/shows` `/mnt/movies`, Decypharr's
staging dir at `/mnt/downloads`, and the DFS mount
at `/mnt/decypharr`, so the symlinks Decypharr stages into its download folder resolve at the
same place everywhere. Then in
Jellyfin add the libraries the same way ([Jellyfin setup](jellyfin) covers libraries plus the
transcode policy). Also set Jellyfin → Playback → **Transcode path**
to `/transcodes` (a tmpfs — transcode scratch never hits disk; this edition transcodes in
software, so keep the library direct-play friendly).

If those paths look empty inside a container, check mount propagation
([Decypharr](decypharr#visibility-of-the-mount)).

## Imports are symlinks, not hardlinks

There's no local download to hardlink here: Decypharr hands the \*arrs a **symlink** into its
FUSE mount, and importing renames that link into the root folder — the payload never lands on
disk, it streams from the debrid provider at playback (FUSE debrid mounts can't hardlink
anyway: `link()` isn't implemented). Two constraints follow:

- **Keep Decypharr's download folder and the \*arr root folders on the same filesystem.** The
  staging dir `/mnt/downloads` and the roots `/mnt/shows` + `/mnt/movies` are all real dirs on
  the shared bind, so the import is a rename of a tiny symlink — instant. If they straddle
  filesystems the \*arrs fall back to copying, and copying a symlink *dereferences* it: the
  entire file gets pulled from debrid onto local disk.
- **Every consumer must resolve the symlink target at the same path.** What's stored in the
  library is an absolute path into the mount, so `sonarr`, `radarr`, `bazarr`, and `jellyfin`
  all bind `/mnt/decypharr` at the identical path. Change it in one place and that app sees a
  library full of dangling links.

## Prowlarr application sync

`just wire` provisions Prowlarr's Sonarr and Radarr application links and enables full sync.
Every indexer added in Prowlarr, including the self-hosted [Comet (Local)](comet) indexer, is then pushed to both apps.
Choose and test indexers in Prowlarr; there is no reason to recreate the application links by
hand unless you intentionally changed them.

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

## Managing from your phone

**Ruddarr** ([ruddarr.com](https://ruddarr.com)) is a free, open-source **iOS companion app**
for Radarr and Sonarr — browse the library and calendar, kick off searches, act on the queue
or history. It's a *client*, not a service: nothing runs on the server. Point it at each
instance's **Application URL**: with Tailscale on the phone, `https://radarr.<DOMAIN>` /
`https://sonarr.<DOMAIN>` resolve to the box's tailnet address ([Tailnet DNS](../tailnet)) — no
public A records, no extra auth (the tailnet is the gate). The app handles HTTPS and
reverse-proxy headers; the panels' own logins and CrowdSec still apply, so they stay
admin-only — the app is just another client.
