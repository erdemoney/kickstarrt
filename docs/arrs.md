---
title: The *arrs
nav_order: 6
---

# The \*arrs: networking and app wiring

First-run setup happens over the tailnet while nothing is public
([Quickstart §9](quickstart#9-set-up-the-apps)) — open `https://radarr.<DOMAIN>` and friends
from any tailnet device. Run `just wire --dry-run` first to preview the repeatable changes,
then run `just wire` to review and confirm each checkpoint. The remaining GUI steps are
documented below.

## Automated wiring

After the first-run admin accounts and Decypharr wizard are complete, `just wire` can
reconcile the repeatable cross-service links through the applications' REST APIs. It does
not edit `config.xml`, `config.json`, or Decypharr's `auth.json`; those files are read only
to bootstrap API credentials. Requests run from inside the containers, so the internal
service names remain private.

The default mode is interactive. It discovers the current configuration, displays each
service-level change with secrets redacted, and asks for confirmation before applying it.
It stops after a declined or failed checkpoint rather than cascading through a partial setup.

```bash
just wire --dry-run   # discover and display planned changes
just wire             # review and confirm each checkpoint
just wire --yes       # non-interactive use after reviewing the dry run
```

The command handles Arr root folders and Decypharr's streaming integrations, Prowlarr's
Sonarr/Radarr application links, Bazarr's Sonarr/Radarr connections, and Recyclarr's native
secret file plus initial sync. Jellyfin, Seerr, subtitle providers,
language profiles, indexer choices, and the Decypharr provider/mount wizard remain GUI steps
because they require user-specific choices or first-run authentication.

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
| jellyfin  | `http://jellyfin:8096`  | 8096 | Jellyfin → Dashboard → API Keys (generate one)  |
| seerr     | `http://seerr:5055`     | 5055 | (outbound only)                                 |
| radarr    | `http://radarr:7878`    | 7878 | Settings → General → API Key                    |
| sonarr    | `http://sonarr:8989`    | 8989 | Settings → General → API Key                    |
| prowlarr  | `http://prowlarr:9696`  | 9696 | Settings → General → API Key                    |
| recyclarr | —                      | —    | automatic — nothing to paste (see below)        |
| bazarr    | `http://bazarr:6767`    | 6767 | (outbound only)                                 |
| decypharr | `http://decypharr:8282` | 8282 | Settings → API token (shown once after wizard)  |
| zilean    | `http://zilean:8181`    | 8181 | (indexer; no API key — see [Indexers](indexers)) |

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
Every indexer added in Prowlarr, including [Torrentio](indexers), is then pushed to both apps.
Choose and test indexers in Prowlarr; there is no reason to recreate the application links by
hand unless you intentionally changed them.

## Seerr → Jellyfin + Radarr + Sonarr (requests)

1. Seerr → Settings → **Jellyfin**: server name, URL `http://jellyfin:8096`, and an **API key
   generated on the Jellyfin server** (Dashboard → API Keys — the admin account is created on
   Jellyfin's first login).
2. Seerr → **Radarr** and **Sonarr**: enable, add `http://radarr:7878` / `http://sonarr:8989`
   + API keys, pick the shipped **Direct Play** quality profile and the root folder for each.
3. Users can now request via Seerr, which pushes to Radarr/Sonarr.

## Bazarr → Sonarr/Radarr (subtitles)

Bazarr's Sonarr/Radarr connections are configured by `just wire`. It reads Bazarr's own API
key, submits only the two connection blocks through `/api/system/settings`, and preserves all
other Bazarr settings. Bazarr only fetches subtitles for titles added **after** a language
profile is assigned — the easy-to-forget step.

1. Create a language profile (Languages → manage), then assign it in the Sonarr/Radarr
   library views via **Mass Edit**.
2. **Subtitle providers** (the fiddly part):
   - **OpenSubtitles.com** — primary; the old `.org` API is shut down. Create an account,
     generate an **API key** on your profile page, enter username + API key. Free tier is
     rate-limited (~20 downloads/day); VIP removes the cap.
   - **subdl.com** — free fallback; grab an API key from your account panel (~2,000
     searches/day).
   - **Whisper (optional)** — AI-generated fallback when nothing clears a minimum score;
     needs a separate whisper ASR service.
4. Rank providers by preference and raise each language's **minimum score** if subs arrive
   out of sync or machine-translated. Subtitle folder: **Alongside media file**.

## Quality profiles (Recyclarr - automatic)

[Recyclarr](https://recyclarr.dev) syncs the tracked TRaSH-Guide profiles into Radarr and Sonarr.
`just wire` creates its private API-key file and runs the first sync; the container then syncs
daily. Before wiring, it waits quietly for the file to exist.

The YAML under `data/recyclarr/configs/` is the source of truth. Edit it when you want to tune
quality scores, then run the sync manually if you do not want to wait for the next scheduled run:

```bash
docker compose -f stacks/media-server/compose.yaml exec recyclarr recyclarr sync
```

Choose **Direct Play** wherever an app asks for a quality profile. If you regenerate an Arr API
key, run `just wire` again.

### Direct Play (Anime) companion profile (Sonarr)

Sonarr also ships a **Direct Play (Anime)** profile (TRaSH's `[Anime] Remux-1080p` recipe)
for anime series inside the same instance. It differs from **Direct Play** in the ways that
matter to anime: `Bluray-1080p Remux` and `Bluray-1080p` are merged into one tier (and are the
upgrade ceiling), HDTV resolutions are folded into the WEB tiers (anime HDRips often tag
themselves HDTV), and SeaDex-driven **Anime BD/Web tier** Custom Formats rank release groups
instead of the general tiers. x265 is *not* penalized — anime BD encodes are nearly always
x265 10-bit — but the same `-10000` codec/disk-image never-grab rules apply, and
dubs-only/raw/LQ anime groups are rejected.

Nothing else to set up: both profiles arrive with the same automatic sync. When you add an
anime series in Sonarr (set its **Series Type** to *Anime*), pick the **Direct Play (Anime)**
profile for it; regular shows keep **Direct Play**. Tuning knobs live in the header comments
of `data/recyclarr/configs/sonarr.yml` (e.g. score `Anime Dual Audio` / `Uncensored`
positively if the household prefers them).

> Migrating from the old Profilarr setup? Nothing to migrate — its container and panel are
> gone; the leftover `data/profilarr` dir is inert and safe to delete.

## Managing from your phone

**Ruddarr** ([ruddarr.com](https://ruddarr.com)) is a free, open-source **iOS companion app**
for Radarr and Sonarr — browse the library and calendar, kick off searches, act on the queue
or history. It's a *client*, not a service: nothing runs on the server. Point it at each
instance's **Application URL**: with Tailscale on the phone, `https://radarr.<DOMAIN>` /
`https://sonarr.<DOMAIN>` resolve to the box's tailnet address ([Tailnet DNS](tailnet)) — no
public A records, no extra auth (the tailnet is the gate). The app handles HTTPS and
reverse-proxy headers; the panels' own logins and CrowdSec still apply, so they stay
admin-only — the app is just another client.
