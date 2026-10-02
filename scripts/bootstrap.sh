#!/usr/bin/env bash
#
# bootstrap.sh - one-shot bootstrap for a fresh VPS (see docs/quickstart.md).
#
# Installs, idempotently: Tailscale, git, just, Docker (with the compose
# plugin), and adds the invoking user to the `docker` group. Only needs curl.
# Cross-distro: Debian/Ubuntu (apt), Fedora/RHEL (dnf/yum),
# openSUSE (zypper), Arch (pacman) and Alpine (apk).
#
#     curl -fsSL https://raw.githubusercontent.com/erdemoney/kickstarrt/main/scripts/bootstrap.sh | sudo bash
#
# At the end the script joins the box to your tailnet: it prints the auth URL
# and waits up to 120s for you to approve it, then prints the box's tailnet
# address - your only SSH address. Approval is always yours; if the window
# passes, it falls back to printing the manual `sudo tailscale up` step.
#
# It deliberately does NOT install UFW or ufw-docker, or touch any firewall
# rules. Nothing here can lock a fresh box out or silently dismantle a distro
# image's shipped firewall.

set -euo pipefail

has() { command -v "$1" >/dev/null 2>&1; }

msg()  { printf '[prereq] %s\n' "$*"; }
ok()   { printf '[ok]     %s\n' "$*"; }
skip() { printf '[skip]   %s\n' "$*"; }
warn() { printf '[warn]   %s\n' "$*"; }

# Re-run as root (that's what installing system packages needs), remembering
# who should end up in the docker group.
if [ "$(id -u)" -ne 0 ]; then
    if ! has sudo; then
        printf 'needs root or sudo: run "sudo bash %s"\n' "$(basename "$0")" >&2
        exit 1
    fi
    exec sudo -E bash "$0" "$@"
fi

REAL_USER="${SUDO_USER:-root}"
TS_IP=""

PM=""
PM_DEPS=()
detect_pm() {
    if has apt-get; then
        PM=apt;    PM_DEPS=(apt-get install -y)
        # ufw can ask debconf questions and this script is usually piped in with
        # no controlling tty; silence the noninteractive fallback song-and-dance.
        export DEBIAN_FRONTEND=noninteractive
    elif has dnf; then
        PM=dnf;    PM_DEPS=(dnf install -y)
    elif has yum; then
        PM=yum;    PM_DEPS=(yum install -y)
    elif has zypper; then
        PM=zypper; PM_DEPS=(zypper install -y)
    elif has pacman; then
        PM=pacman; PM_DEPS=(pacman -Sy --noconfirm)
    elif has apk; then
        PM=apk;    PM_DEPS=(apk add --no-cache)
    fi
    if [ -z "$PM" ]; then
        warn "no supported package manager found - distro-package fallbacks will not work"
    fi
}

install_tailscale() {
    msg "Tailscale"
    if has tailscale; then
        skip "already installed ($(tailscale version | head -n 1))"
        return
    fi
    if ! curl -fsSL https://tailscale.com/install.sh | sh; then
        if [ "$PM" = apk ]; then
            "${PM_DEPS[@]}" tailscale
            warn "Alpine: start the daemon with 'rc-service tailscaled start'"
        fi
    fi
    if has tailscale; then
        ok "installed"
    else
        printf 'tailscale install failed\n' >&2
        exit 1
    fi
}

install_git() {
    msg "git"
    if has git; then
        skip "already installed ($(git --version))"
        return
    fi
    if [ -z "$PM" ]; then
        printf 'cannot install git (no supported package manager)\n' >&2
        exit 1
    fi
    "${PM_DEPS[@]}" git
    if has git; then
        ok "installed ($(git --version))"
    else
        printf 'git install failed\n' >&2
        exit 1
    fi
}

install_just() {
    msg "just"
    if has just; then
        skip "already installed ($(just --version))"
        return
    fi
    if ! curl -fsSL --proto '=https' --tlsv1.2 https://just.systems/install.sh | bash -s -- --to /usr/local/bin; then
        if [ -n "$PM" ]; then
            "${PM_DEPS[@]}" just
        fi
    fi
    if has just; then
        ok "installed ($(just --version))"
    else
        printf 'just install failed\n' >&2
        exit 1
    fi
}

install_docker() {
    msg "Docker + compose plugin"
    if ! has docker; then
        if ! curl -fsSL https://get.docker.com | sh; then
            if [ -n "$PM" ]; then
                "${PM_DEPS[@]}" docker
            else
                printf 'docker install failed (no package-manager fallback)\n' >&2
            fi
        fi
        if has systemctl; then
            systemctl enable --now docker >/dev/null 2>&1 || true
        fi
        if [ "$PM" = apk ]; then
            rc-update add docker default >/dev/null 2>&1 || true
            service docker start >/dev/null 2>&1 || true
        fi
        has docker || { printf 'docker install failed\n' >&2; exit 1; }
    else
        skip "already installed ($(docker --version))"
    fi

    if ! docker compose version >/dev/null 2>&1; then
        case "$PM" in
            apk)  "${PM_DEPS[@]}" docker-cli-compose ;;
            "")   warn "install the docker compose plugin manually" ;;
            *)    "${PM_DEPS[@]}" docker-compose-plugin || warn "compose plugin package not found" ;;
        esac
    fi
    if docker compose version >/dev/null 2>&1; then
        ok "compose ready ($(docker compose version --short))"
    else
        warn "compose plugin missing - 'just up' will need it"
    fi
}

ensure_docker_group() {
    msg "docker group"
    if [ "$REAL_USER" = root ]; then
        skip "running as root - no group membership needed"
        return
    fi
    if id -nG "$REAL_USER" 2>/dev/null | grep -qw docker; then
        skip "$REAL_USER is already a docker member"
        return
    fi
    usermod -aG docker "$REAL_USER"
    ok "$REAL_USER added to docker - log out and back in before 'just up'"
}

join_tailnet() {
    msg "Tailscale join"
    if ! has tailscale; then
        warn "tailscale not installed - nothing to join"
        return
    fi
    if tailscale ip -4 >/dev/null 2>&1; then
        TS_IP="$(tailscale ip -4 | head -n 1)"
        ok "already joined - tailnet address $TS_IP"
        return
    fi
    if [ "$PM" = apk ]; then
        rc-update add tailscaled default >/dev/null 2>&1 || true
        service tailscaled start >/dev/null 2>&1 || true
    fi
    flags=()
    if tailscale up --help 2>/dev/null | grep -q -- --timeout; then
        flags+=(--timeout=120s)
    fi
    if ! tailscale up "${flags[@]}"; then
        warn "not joined within 120s - run 'sudo tailscale up' and approve the URL it prints"
        return
    fi
    TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1)"
    ok "joined - tailnet address $TS_IP"
}

main() {
    msg "prerequisites for $(hostname) ($(uname -m))"
    detect_pm
    install_tailscale
    install_git
    install_just
    install_docker
    ensure_docker_group
    join_tailnet
    printf '\n'
    if [ -n "$TS_IP" ]; then
        if [ "$REAL_USER" = root ]; then
            printf '   ssh <you>@%s   # your only SSH address (OCI default: ubuntu)\n' "$TS_IP"
        else
            printf '   ssh %s@%s   # your only SSH address\n' "$REAL_USER" "$TS_IP"
        fi
    else
        printf '   1. sudo tailscale up   # approve the URL it prints\n'
        printf '   2. tailscale ip -4     # your only SSH address\n'
    fi
    msg 'then continue with docs/quickstart.md: Section 3 to verify SSH over the tailnet, then'
    msg 'Section 6 covers the firewall choice: provider firewall mode or explicit UFW setup.'
}
main "$@"
