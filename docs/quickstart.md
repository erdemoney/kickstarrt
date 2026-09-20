---
title: Quickstart
nav_order: 2
---

# Quickstart

The whole setup, in the order it has to happen. Every command you need is on this page; each
step links to a deeper page for the how-it-works and troubleshooting.

The flow: bring up a fresh VPS, walk in over public SSH **once**, join the box to your
Tailscale tailnet, choose the firewall model, then build the stack and set it up privately over
the tailnet. With either model, keep the application routers tailnet-only until you deliberately
publish a service.

Before you start, have:

- **A VPS** — any provider, ≥ 2 vCPU / 4 GB RAM ([sizing](index)), with SSH access you can
  reach. Bring it up in the next section.
- **A domain you control** — used for every panel URL (`radarr.<DOMAIN>`, …) and the wildcard
  TLS cert, so pick something you can keep. It should be **served by Cloudflare** (DNS records,
  the DNS-01 cert challenge, and R2 backups all live there): move the domain's nameservers to
  Cloudflare first if it isn't already.
- **Cloudflare account** with the domain (and an API token made during configuration; **Cloudflare
  R2** for the optional restic backups).
- **Tailscale account** — you'll approve the box into your tailnet in the next section and
  register the DNS resolver in [§7](quickstart#7-register-the-tailnet-dns-resolver).
- **GitHub account** — the repo is meant to be forked ([§4](quickstart#4-fork-and-clone-the-repository)).
- **A workstation** on the tailnet with a browser — this is where the admin panels are set up.

## 1. Create the VPS

Any provider, any box with ≥ 2 vCPU / 4 GB RAM (sizing notes in the [overview](index)). Use a
**Debian 12** or **Ubuntu LTS** image — every command in this wiki is written for them. On
Oracle Cloud, use **Ubuntu 26.04 Minimal** instead (no Debian image there);
the [OCI appendix](oci) walks the whole creation, including the `443`/`80` ingress rules
you'll need much later.

The one thing you need from the provider: SSH access to the fresh box (a key you injected at
creation, or however the provider does first login).

## 2. Get in: join the tailnet

SSH in over the **public IP** — the one and only time you use it:

```bash
ssh <user>@<PUBLIC-IP>
```

Then bootstrap the box with this repo's setup script. It is **idempotent** (safe to re-run)
and cross-distro, and installs everything the rest of this guide needs — `git`, `just`, Docker
with the compose plugin, `ufw-docker`, and your user in the `docker` group — **and joins the box
your tailnet**:

```bash
curl -fsSL https://raw.githubusercontent.com/erdemoney/kickstarrt-vps/main/scripts/prerequisites.sh | sudo bash
```

The script prints an **auth URL** and waits up to two minutes — open it in a browser and
approve the node. (Missed the window? `sudo tailscale up` prints it again.) It ends by
printing the box's **tailnet address** — a `100.x.y.z` from Tailscale's CGNAT range. That
address is your SSH address from now on.

The script installs the `ufw-docker` executable but does not install UFW or change firewall
rules. Choose the firewall model in [§6](#6-choose-the-firewall-model).

## 3. Verify SSH over the tailnet

From your workstation:

```bash
ssh <user>@100.64.0.3     # the address the script printed
```

Once this works, the public SSH door has done its job — close the provider-side `22` rule in
UFW mode, or keep it deliberately open under your provider-firewall policy. If you use **MagicDNS**,
the box also answers at
`<node>.<tailnet>.ts.net`; fine for SSH, but the stack itself routes on `.DOMAIN` names, so
the `100.x.y.z` address is the one that matters later.

> **Set up your break-glass path now:** confirm that the provider offers a working web console,
> serial console, VNC console, or equivalent out-of-band access, and that its required
> credentials or console key are available. If the box loses Tailscale, this is how you get in
> and run `sudo tailscale up` again; do not rely on public SSH remaining available after
> host-firewall setup. If the provider's console uses a local OS password, set a long random one while
> tailnet SSH still works, without enabling SSH password authentication. On Oracle Cloud,
> Ubuntu images configure no console password by default; the [OCI appendix](oci#3-recovery-the-console-break-glass)
> shows the one-time setup and recovery procedure.

## 4. Fork and clone the repository

Install and authenticate the GitHub CLI. It can create or upload the SSH key used to clone the
private fork:

```bash
sudo apt install gh        # other installers: https://cli.github.com
gh auth login              # choose GitHub.com → SSH; generate or upload a key when offered
```

This repo is meant to be **forked**. Create the fork, then clone it into the standard checkout
directory:

```bash
mkdir -p ~/docker
gh repo fork erdemoney/kickstarrt-vps
gh repo clone <you>/kickstarrt-vps ~/docker/kickstarrt-vps
gh repo edit <you>/kickstarrt-vps --visibility private     # public forks leak any secret you commit
# --- or fork it in the browser ---
```

If you fork in the browser instead, make the fork **private** (Settings → change visibility — a
secret committed to a public fork leaks it to the world), then clone it on the box:

```bash
git clone git@github.com:<you>/kickstarrt-vps.git ~/docker/kickstarrt-vps
cd ~/docker/kickstarrt-vps
```

One housekeeping item first: the `docker` group the bootstrap script put you in only takes
effect in a **new SSH session** — reconnect, then `docker run --rm hello-world` should work
without sudo.

## 5. Configure the stack

Now run `just init` — it creates each stack's private `.env`, detects safe defaults, validates
the values it writes, and prompts only for the settings that need a decision. At any value prompt,
type `?` for a short explanation, an example, and the relevant documentation reference.

- `TAILNET_IP` is auto-filled from `tailscale ip -4`; if the configured address later differs,
  init detects the drift and asks before updating it. Update the Tailscale DNS nameserver too.
- `PUBLIC_BIND` is detected from the default route; if it later differs, init asks before
  changing it. On Oracle Cloud this can be the private VCN/VNIC address, not the public address.
- `CROWDSEC_BOUNCER_API_KEY` is generated for you (random 32-byte key).
- `DOMAIN` is prompted once and synced to every stack; each `SUB_DOMAIN_*` is filled with
  the app name as its default and can be edited in the `.env` files later.
- `ENV_PUID`/`ENV_PGID` use the running user's uid/gid, so container files match your user
  (fallback `1000` if you run as root). If an existing installation uses different IDs, init
  reports the mismatch and keeps them; `just init --force` can explicitly replace them.
- An optional username/password prompt writes `TRAEFIK_DASHBOARD_CREDENTIALS` for the
  [Traefik dashboard](ingress#traefik-dashboard).
- `CLOUDFLARE_DNS_TOKEN` — enter it when ready; `just init` verifies it against Cloudflare.
  Leave it empty to do it later.
- Optionally sets up **restic backups to Cloudflare R2** — answer `y` to be prompted, or skip
  and fill `.env.restic` later ([Maintenance](maintenance)).

It's safe to re-run: values that are already set are kept, so a re-run only asks for what's
missing (e.g. a restic step you deferred) or detects machine values that changed. To re-prompt
optional credentials, run `just init --force`. The full variable list, with comments, is in
`stacks/traefik/.env.example` and `stacks/media-server/.env.example`. The main secrets worth
understanding are:

### `CLOUDFLARE_DNS_TOKEN` — Cloudflare (wildcard TLS)

This token is the entire Let's Encrypt prerequisite: DNS-01 is how Traefik proves ownership of
`*.DOMAIN` ([Ingress → Certificates](ingress#certificates)).

1. Open [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) → **Create Token** →
   **Create custom token**, with two permissions on `DOMAIN`:
    - **Zone → Zone → Read** — resolves the domain to a zone ID before any record can be edited.
   - **Zone → DNS → Edit** — creates and deletes the `_acme-challenge` TXT records.
2. **Zone Resources** → **Include** → **Specific zone** → your `DOMAIN` (least privilege —
   not "All zones").
3. Create — `just init` verifies the token against Cloudflare's API right after you enter it,
   so a bad paste or revoked token fails immediately. To re-check an existing token:

```bash
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer <token>"   # expect "status": "active"
```

### `TRAEFIK_DASHBOARD_CREDENTIALS` — htpasswd blob

A `user:hash` pair for `https://traefik.<DOMAIN>`, not a token:

```bash
docker run --rm httpd:2.4-alpine htpasswd -nbB user 'ChangeMe-strong-password'
```

`.env` gotcha: the `$2y$...` hash breaks compose interpolation — **quote the whole value in
single quotes**:

```
TRAEFIK_DASHBOARD_CREDENTIALS='user:$2y$05$abcdefghijklmnopqrstuvwxyz0123456789'
```

### `CROWDSEC_BOUNCER_API_KEY` — local random key

Already generated by `just init`; by hand it's `openssl rand -hex 32`. No dashboard to sign up
for — CrowdSec and Traefik use it to authenticate with each other. It must be set **before**
`just up`; after changing it, recreate the `crowdsec` and `traefik` containers
(`just update-all`). Details in [Security](security).

## 6. Choose the firewall model

The provider firewall and the host firewall are separate layers. Choose one before the first
boot; the stack's application routers remain tailnet-only by default either way.

### Provider firewall mode

Use this mode if you will keep the stack private and manage inbound rules at the provider. Deny
public inbound `22`, `53`, `80`, and `443` in the provider firewall, except for any deliberate
temporary SSH access during setup. Keep a working provider console as the break-glass path.

This mode does not install UFW or change host firewall rules. `just health` reports that the host
firewall is not configured; it cannot inspect or verify the provider firewall.

### UFW mode

Use this mode for host-level defense in depth or before exposing services publicly. **Before
changing the firewall:** verify that you can access the provider's web, VNC, or serial console
and that its break-glass credentials work. If the tailnet or SSH session fails, that console is
the recovery path.

On Debian or Ubuntu, install UFW and its man-page dependency:

```bash
sudo apt update
sudo apt install -y ufw man-db
```

Apply the tailnet-only baseline. These are ordinary UFW commands and are intentionally shown
before they are run:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 100.64.0.0/10 to any port 22 proto tcp
sudo ufw allow from 100.64.0.0/10 to any port 53 proto tcp
sudo ufw allow from 100.64.0.0/10 to any port 53 proto udp
sudo ufw allow from 100.64.0.0/10 to any port 443 proto tcp
sudo ufw --force enable
```

Docker-published ports use the `FORWARD` path, which UFW's normal incoming rules do not inspect.
Install the already-provided [ufw-docker](https://github.com/chaifeng/ufw-docker) integration,
then verify it:

```bash
sudo ufw-docker install --system
sudo systemctl restart ufw
sudo ufw-docker check
```

On a provider with a different package manager, install the equivalent UFW package first.
The bootstrap script in [§2](#2-get-in-join-the-tailnet) already installs the `ufw-docker`
executable, so this is only needed when you set UFW up by hand. In that case, follow the
[official ufw-docker install](https://github.com/chaifeng/ufw-docker/tree/master#install)
before running the commands above.

On **Oracle Cloud**, delete the wizard's default `22` ingress rule after tailnet SSH is confirmed
(VCN → Default Security List → the `TCP 22 / 0.0.0.0/0` rule → Delete). SSH then has exactly one
way in: your tailnet. In provider firewall mode, make the equivalent provider rule change
yourself and keep any deliberate public SSH access.

## 7. Register the tailnet DNS resolver

One-time step in the Tailscale admin console, done **before** first boot so every app answers
by name the moment the stack is up. The resolver is the CoreDNS container in the traefik
stack, answering `*.DOMAIN` with the box's tailnet address — mechanics and assumptions in
[Tailnet DNS](tailnet).

```bash
just dns     # prints the nameserver value to paste (your TAILNET_IP)
```

1. [Tailscale Admin → DNS](https://login.tailscale.com/admin/dns) → **Nameservers** →
   **Add nameserver** → **Custom**.
2. Enter the value `just dns` printed (a `100.x.y.z`).
3. Constrain it: **"Only send names in these domains"** → add your `DOMAIN` (*not* the
   `.ts.net` name).
4. Leave **MagicDNS** on and **"Override local DNS"** off. Save, then refresh DNS on your
   devices — rejoin the tailnet, or flush: `sudo dscacheutil -flushcache` (macOS),
   `sudo systemctl restart systemd-resolved` (Linux), `ipconfig /flushdns` (Windows).

Until the stack boots (next step), `*.DOMAIN` lookups won't answer: split DNS intercepts the
domain with no fallback, and nothing is listening yet. Expected — it heals at first boot.

## 8. First boot

```bash
just up
```

### Verify the first boot

`just up` runs preparation, creates the networks and runtime directories, and starts both stacks.
The tracked Traefik and CoreDNS configuration is mounted directly; CoreDNS receives its domain
and tailnet address through the container environment. Use the read-only health panel for the
routine checks:

```bash
just health
```

From a tailnet device, the expected result is that each configured hostname opens over HTTPS and
the wildcard certificate is valid. Continue with app setup even if Recyclarr is waiting for
`just wire`; that is expected before its secrets exist.

## 9. Set up the apps

Everything is reachable by name over the tailnet and **nothing is public yet** — that's the
window to do first-run setup, while no app can be reached by strangers. The order matters:
Decypharr first, because the \*arrs need its live mount (root folders) and the wiring assumes
it's configured.

1. **Decypharr** — run the wizard: admin account, debrid provider + API key, mount at
   `/mnt/decypharr` → [Decypharr](decypharr#first-run-setup-wizard).
2. **\*arrs** — run `just wire` on the box. It provisions streaming integrations, root folders,
   Prowlarr sync, Bazarr connections, Recyclarr's API secrets, and the Sonarr/Radarr → Jellyfin
   scan connections (creating the Jellyfin admin account and API key on first run, or minting the
   key from the existing admin credentials). Finish
   language profiles and indexer choices in the GUI → [The \*arrs](arrs).
3. **Jellyfin** — a fresh `just wire` already created the admin account and API key, so finish the
   setup: add the libraries under `/mnt/shows` and `/mnt/movies` and set the transcode path → [Jellyfin](jellyfin).
4. **Seerr** — connect Jellyfin at `http://jellyfin:8096`, then connect Radarr and Sonarr with
   their internal URLs and API keys → [Seerr setup](seerr).
5. **Indexers** — add at least one debrid indexer such as Torrentio; AltHub can be
   added for TorBox Usenet streaming. The self-hosted Comet (Local) indexer is already
   wired into Prowlarr by `just wire` → [Indexers](indexers).

`just wire --dry-run` previews the changes, and `just wire` applies each confirmed checkpoint.
Minimum before going public: every app has its admin account and auth on — [the security
gate](ingress#the-security-gate).

## 10. Verify the security services

CrowdSec, Traefik, Tailscale, UFW, and the Docker forwarding gate are checked by the same
read-only panel:

```bash
just health
```

## 11. Backups and updates

Set up encrypted offsite backups before exposing the service publicly:

```bash
just init              # answer yes to the Cloudflare R2 backup step
just backup-init
just backup
just backup-schedule   # optional daily systemd timer (backup + prune)
```

See [Maintenance](maintenance) for R2 credentials, alternate backends, restores, and retention.

Enable the Renovate workflow once on GitHub:

```bash
gh secret set RENOVATE_TOKEN
```

Then run the **Renovate** workflow once from GitHub Actions. Review its pull requests normally;
after merging one, update the server with `git pull && just update-all`. See [Updates & CI](updates).

## 12. Go public (last)

When every app is set up and has auth on: add the two hostnames users actually need, then open
the serving ports — in that order.

1. Enable the public Traefik routers for the services you want to publish. The default is
   tailnet-only, and this changes routing only — it does not touch UFW or DNS:

```bash
just public enable jellyfin seerr
```

   Use `just public status` to review the current router selection. In Cloudflare DNS, add **A
   records** for each enabled hostname, such as `seerr.<DOMAIN>` and `jellyfin.<DOMAIN>`, pointing
   at the VPS's **public IP**, **Proxy status: DNS only** (grey cloud — never proxied,
   [why](faq#why-cant-i-proxy-media-through-cloudflare)). Detailed steps in
   [Ingress → Adding a public hostname](ingress#adding-a-public-hostname-dns-record).
 2. In **UFW mode**, open the public ports separately:

```bash
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp
```

These are the real network rules: `443` serves the enabled apps and `80` serves only the
http → https redirect. The A records above are the other half of the door. In provider firewall
mode, open the equivalent ports in the provider firewall instead.

Because the [ufw-docker](https://github.com/chaifeng/ufw-docker) gate routes container traffic through UFW, these two rules are exactly
what lets Docker-forwarded `:443`/`:80` through — the same syntax that opened the tailnet
doors in §6.

That's it — the enabled services are public on their configured hostnames: Cloudflare DNS → VPS `:443` →
Traefik → CrowdSec → the apps. Admin panels stay off the public DNS and are reached over the
tailnet by name ([Tailnet DNS](tailnet)). Fully reversible: delete the records and remove the
corresponding provider/UFW port rules. To remove a public router, run `just public disable
<service>`; this does not change the firewall.

From here: [Indexers](indexers) and [Services](services) can be set up any time after the
stack is up; [Updates & CI](updates) and [Maintenance](maintenance) are the ongoing-ops pages.
