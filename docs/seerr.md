---
title: Seerr
nav_order: 8
---

# Seerr: media requests

Seerr is the user-facing request portal for the stack. Users browse available movies and
shows, submit requests, and Seerr sends them to Radarr or Sonarr. Those applications then
use the normal indexer and Decypharr workflow to acquire and import the media.

## 1. First login

Open `https://seerr.<DOMAIN>` from a tailnet device during setup. Seerr's first-login wizard
creates its administrator account and lets you sign in with Jellyfin. `just wire` can complete
this wizard for you: it detects a fresh Seerr, logs in to Jellyfin as an admin (reusing the
credentials it already gathered in the same run, so it never prompts twice), creates the Seerr
admin account, and marks setup complete. Run `just wire` in a terminal — `--yes` cannot prompt
for those credentials, so it skips Seerr with an error if first-run is still needed. The Seerr
panel is tailnet-only by default. After setup, use `just public enable seerr` if you want to
publish it, then separately configure DNS and UFW ([Ingress](ingress)).

Seerr stores its configuration under `data/seerr/config`, so recreating the container
does not remove its users or integrations.

## 2. Connect Jellyfin

Seerr uses Jellyfin for user authentication and library availability. `just wire` reconciles
this connection and the libraries Seerr needs:

- points Seerr at `http://jellyfin:8096` using the connection that Seerr's own Jellyfin login
  established (the Jellyfin API key stays Seerr-managed — it mints a dedicated key at login),
- syncs and **enables every Jellyfin library** so Seerr can fill requests; create the media
  libraries first in Jellyfin → Dashboard → Media Libraries, otherwise wire reports none found,
- keeps Seerr's media server type set to Jellyfin.

Manual setup (fallback): in Seerr open **Settings → Jellyfin**, use `http://jellyfin:8096` and
an API key generated in Jellyfin → Dashboard → API Keys, then test and save.

Use the internal service URL, not `https://jellyfin.<DOMAIN>` or `localhost`. All containers
share the `internal` Docker network ([The \*arrs](arrs#docker-networking)).

## 3. Connect Radarr and Sonarr

`just wire` creates and reconciles the two Seerr media-manager connections:

| Application | Internal URL             | Root folder    |
| ----------- | ------------------------ | -------------- |
| Radarr      | `http://radarr:7878`     | `/mnt/movies`  |
| Sonarr      | `http://sonarr:8989`     | `/mnt/shows`   |

It matches each Seerr server by hostname and port, re-asserts the connection fields (internal
URL, API key from the \*arr, root folder, sync enabled), and pins the shipped **Direct Play**
quality profile when the server is first created. Later runs leave the profile — and any anime or
language choices you make in the Seerr UI — untouched.

Manual setup (fallback): under **Settings** add each application, enable the connection, enter
the internal URL and its API key (Settings → General → API Key), select **Direct Play**, select
the root folder, then test and save.

The same wiring is documented with the rest of the service integrations in [The \*arrs](arrs#seerr--jellyfin--radarr--sonarr-requests).

### Troubleshooting

- **`INVALID_URL` (HTTP 404) from `/api/v1/auth/jellyfin`.** Seerr builds the Jellyfin URL as
  `ip:port + urlBase`; an omitted (not empty) `urlBase` stringifies to `"...:8096undefined"`,
  which never connects. `just wire` sends `urlBase: ""` explicitly, so this only recurs if you
  call Seerr's login endpoint by hand — always pass `urlBase` (empty string).

## 4. Request flow

After the integrations are connected, users can search Seerr and request movies or shows.
Seerr pushes approved requests to Radarr or Sonarr, which handle indexers and debrid streaming
imports. Once the item is available in the configured library, Jellyfin scans it and Seerr
updates the request status.

Keep Seerr, Jellyfin, Radarr, and Sonarr on the same internal network and use their service
names for app-to-app connections. Public hostnames are for browser access only.