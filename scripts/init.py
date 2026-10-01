#!/usr/bin/env python3
"""Create and safely configure the stack environment files."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .common import (
    EnvFile,
    ROOT,
    ScriptError,
    create_env,
    detect_public_ipv4,
    detect_tailscale_ipv4,
    validate_hostname,
    validate_subdomain,
)


TRAEFIK_ENV = ROOT / "stacks" / "traefik" / ".env"
MEDIA_ENV = ROOT / "stacks" / "media-server" / ".env"
RESTIC_ENV = ROOT / ".env.restic"
HUNT_ENV = ROOT / ".env.hunt"


@dataclass(frozen=True)
class Prompt:
    label: str
    explanation: str
    example: str
    doc: str


def prompt(
    details: Prompt,
    current: str = "",
    *,
    secret: bool = False,
    default: str = "",
    validator: Callable[[str], str] | None = None,
) -> str:
    """Prompt with inline help and retryable validation."""
    while True:
        suffix = f" [{current}]" if current else (f" [{default}]" if default else "")
        try:
            answer = (
                getpass.getpass(f"{details.label}{suffix} (or ? for help): ")
                if secret
                else input(f"{details.label}{suffix} (or ? for help): ")
            )
        except EOFError:
            answer = ""
        if answer.strip() == "?":
            print(f"\n{details.label}")
            print(f"  {details.explanation}")
            print(f"  Example: {details.example}")
            print(f"  More help: {details.doc}\n")
            continue
        value = answer or current or default
        if not value and validator is None:
            return value
        if validator is None:
            return value
        try:
            return validator(value)
        except ScriptError as exc:
            print(f"Invalid value: {exc}")
            print(f"More help: {details.doc}")


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{suffix}] ").strip().lower()
    except EOFError:
        return default
    return answer in {"y", "yes"} if answer else default


def valid_ip(value: str, label: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:
        raise ScriptError(f"invalid {label}: {value!r}") from exc


DOMAIN_PROMPT = Prompt(
    "Domain",
    "The base domain used for every service hostname and TLS certificate.",
    "example.com",
    "docs/quickstart.md#4-fork-clone-and-fill-the-secrets",
)
TAILNET_PROMPT = Prompt(
    "Tailscale IPv4 address",
    "The VPS address reachable through Tailscale; admin panels and DNS use this address.",
    "100.64.0.3",
    "docs/tailscale.md",
)
PUBLIC_BIND_PROMPT = Prompt(
    "Public bind IPv4 address",
    "The local VPS address that the provider maps to the Internet. On Oracle this may be the private VCN address.",
    "203.0.113.10 or 10.0.0.5",
    "docs/services/traefik.md#public-access",
)
DASHBOARD_USER_PROMPT = Prompt(
    "Dashboard username",
    "The username required to open the Traefik dashboard over the tailnet.",
    "admin",
    "docs/services/traefik.md#configuration-and-dashboard",
)
DASHBOARD_PASSWORD_PROMPT = Prompt(
    "Dashboard password",
    "A strong password for the Traefik dashboard. It is stored only as a hash.",
    "a unique password",
    "docs/services/traefik.md#configuration-and-dashboard",
)
CLOUDFLARE_PROMPT = Prompt(
    "Cloudflare DNS API token (blank to skip)",
    "A least-privilege token with Zone Read and DNS Edit for your domain, used for wildcard certificates.",
    "paste the token from Cloudflare",
    "docs/cloudflare.md#api-token-for-certificates",
)
R2_ACCOUNT_PROMPT = Prompt(
    "R2 account ID",
    "The Cloudflare account ID shown under R2 Usage and Account Details.",
    "0123456789abcdef0123456789abcdef",
    "docs/maintenance.md#cloudflare-r2-the-documented-path",
)
R2_BUCKET_PROMPT = Prompt(
    "R2 bucket",
    "The existing R2 bucket that will store encrypted restic snapshots.",
    "media-server-restic",
    "docs/maintenance.md#cloudflare-r2-the-documented-path",
)
R2_ACCESS_PROMPT = Prompt(
    "R2 access key ID",
    "The access key from a Cloudflare R2 API token with Object Read & Write permission.",
    "paste the access key ID",
    "docs/maintenance.md#cloudflare-r2-the-documented-path",
)
R2_SECRET_PROMPT = Prompt(
    "R2 secret access key",
    "The secret paired with the R2 access key. It is stored in the private .env.restic file.",
    "paste the secret access key",
    "docs/maintenance.md#cloudflare-r2-the-documented-path",
)
RESTIC_PASSWORD_PROMPT = Prompt(
    "Restic encryption password",
    "The password needed to decrypt every backup. Store it safely outside this server.",
    "a unique backup password",
    "docs/maintenance.md#cloudflare-r2-the-documented-path",
)
USENET_HOST_PROMPT = Prompt(
    "Usenet server hostname",
    "The TLS-capable news server hostname provided by your Usenet provider.",
    "news.example.net",
    "https://www.infinidysk.com/configuration/usenet/",
)
USENET_PORT_PROMPT = Prompt(
    "Usenet server port",
    "Use the port specified by your provider; 563 is the common TLS port.",
    "563",
    "https://www.infinidysk.com/configuration/usenet/",
)
USENET_USER_PROMPT = Prompt(
    "Usenet username",
    "The username for your news-server account. It is stored in the private media .env file.",
    "provider account username",
    "https://www.infinidysk.com/configuration/usenet/",
)
USENET_PASSWORD_PROMPT = Prompt(
    "Usenet password",
    "The password for your news-server account. It is stored in the private media .env file.",
    "provider account password",
    "https://www.infinidysk.com/configuration/usenet/",
)
USENET_CONNECTIONS_PROMPT = Prompt(
    "Usenet connection allowance",
    "Enter the actual concurrent connection allowance from your provider plan.",
    "20",
    "https://www.infinidysk.com/configuration/usenet/",
)


def valid_id(value: str, label: str) -> str:
    if not value.isdigit() or not 0 <= int(value) <= 65535:
        raise ScriptError(
            f"invalid {label}: {value!r}; expected an integer from 0 to 65535"
        )
    return value


def valid_port(value: str) -> str:
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise ScriptError("expected a TCP port from 1 to 65535")
    return value


def valid_connections(value: str) -> str:
    if not value.isdigit() or not 1 <= int(value) <= 500:
        raise ScriptError("expected a connection allowance from 1 to 500")
    return value


def valid_tls(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "yes", "no", "y", "n"}:
        raise ScriptError("expected yes or no")
    return "true" if normalized in {"true", "yes", "y"} else "false"


def non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ScriptError("value must not be empty")
    return value


def compose_env_literal(value: str) -> str:
    """Quote a .env value as a Compose literal, escaping embedded apostrophes."""
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ScriptError("Usenet settings cannot contain newlines or NUL characters")
    return "'" + value.replace("'", "\\'") + "'"


def provider_from_env(media: EnvFile) -> dict[str, object] | None:
    raw = media.get("INFINIDYSK_PROVIDERS")
    if not raw:
        return None
    # EnvFile removes the outer quote pair. Compose treats `\\'` as an escaped
    # apostrophe inside a single-quoted value; restore it before parsing the JSON.
    raw = raw.replace("\\'", "'")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScriptError(
            "INFINIDYSK_PROVIDERS is not valid JSON; run `just init --force` to replace it"
        ) from exc
    providers = value.get("Providers") if isinstance(value, dict) else None
    if (
        not isinstance(providers, list)
        or len(providers) != 1
        or not isinstance(providers[0], dict)
    ):
        raise ScriptError("INFINIDYSK_PROVIDERS must contain exactly one provider")
    return providers[0]


def configure_infinidysk(media: EnvFile, force: bool, changes: list[str]) -> None:
    provider = provider_from_env(media)
    if provider is None or force:
        host = prompt(
            USENET_HOST_PROMPT,
            str((provider or {}).get("Host", "")),
            validator=lambda value: validate_hostname(value, "Usenet server hostname"),
        )
        port = prompt(
            USENET_PORT_PROMPT,
            str((provider or {}).get("Port", "563")),
            validator=valid_port,
            default="563",
        )
        tls = prompt(
            Prompt(
                "Use TLS for the Usenet connection?",
                "TLS is strongly recommended when supported by your news server.",
                "yes",
                "https://www.infinidysk.com/configuration/usenet/",
            ),
            str((provider or {}).get("UseSsl", "true")),
            validator=valid_tls,
            default="true",
        )
        username = prompt(
            USENET_USER_PROMPT,
            str((provider or {}).get("User", "")),
            validator=non_empty,
        )
        password = prompt(
            USENET_PASSWORD_PROMPT,
            secret=True,
            validator=non_empty,
        )
        connections = prompt(
            USENET_CONNECTIONS_PROMPT,
            str((provider or {}).get("MaxConnections", "")),
            validator=valid_connections,
        )
        provider = {
            "Type": 1,
            "Host": host,
            "Port": int(port),
            "UseSsl": tls == "true",
            "User": username,
            "Pass": password,
            "MaxConnections": int(connections),
            "Nickname": "primary",
        }
        serialized = json.dumps({"Providers": [provider]}, separators=(",", ":"))
        if media.set("INFINIDYSK_PROVIDERS", compose_env_literal(serialized)):
            changes.append("InfiniDysk Usenet provider")

    if not media.get("INFINIDYSK_API_KEY"):
        key = secrets.token_urlsafe(32)
        media.set("INFINIDYSK_API_KEY", key)
        changes.append("InfiniDysk API key")


def detected_ids() -> tuple[str, str]:
    uid = os.getuid() or 1000
    gid = os.getgid() or 1000
    if uid == 0:
        uid = 1000
    if gid == 0:
        gid = 1000
    return str(uid), str(gid)


def detect_tailscale() -> str:
    return detect_tailscale_ipv4()


def detect_public_bind() -> str:
    return detect_public_ipv4()


def verify_cloudflare(token: str) -> bool:
    request = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return b'"status":"active"' in response.read()
    except (OSError, urllib.error.URLError):
        return False


def hash_dashboard_password(user: str, password: str) -> str:
    try:
        result = subprocess.run(
            ("openssl", "passwd", "-apr1", "-stdin"),
            input=password + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"'{user}:{result.stdout.strip()}'"
    except OSError:
        pass
    try:
        result = subprocess.run(
            (
                "docker",
                "run",
                "--rm",
                "-i",
                "httpd:2.4-alpine",
                "htpasswd",
                "-niB",
                user,
            ),
            input=password + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScriptError(f"could not hash dashboard password: {exc}") from exc
    if result.returncode != 0 or ":" not in result.stdout:
        raise ScriptError(
            "could not hash dashboard password; install openssl or Docker"
        )
    return f"'{result.stdout.strip()}'"


def configure_env(force: bool) -> list[str]:
    create_env(TRAEFIK_ENV.with_name(".env.example"), TRAEFIK_ENV)
    create_env(MEDIA_ENV.with_name(".env.example"), MEDIA_ENV)
    create_env(ROOT / ".env.restic.example", RESTIC_ENV)
    create_env(ROOT / ".env.hunt.example", HUNT_ENV)
    traefik = EnvFile(TRAEFIK_ENV)
    media = EnvFile(MEDIA_ENV)
    restic = EnvFile(RESTIC_ENV)
    changes: list[str] = []

    domain = traefik.get("DOMAIN")
    if not domain:
        domain = prompt(
            DOMAIN_PROMPT, validator=lambda value: validate_hostname(value, "domain")
        )
    else:
        try:
            domain = validate_hostname(domain, "domain")
        except ScriptError as exc:
            print(f"Invalid existing value: {exc}")
            domain = prompt(
                DOMAIN_PROMPT,
                domain,
                validator=lambda value: validate_hostname(value, "domain"),
            )
    for env in (traefik, media):
        if env.set("DOMAIN", domain):
            changes.append("DOMAIN")

    tailnet = traefik.get("TAILNET_IP")
    detected_tailnet = detect_tailscale()
    if not tailnet:
        tailnet = detected_tailnet
    if not tailnet:
        tailnet = prompt(
            TAILNET_PROMPT, validator=lambda value: valid_ip(value, "TAILNET_IP")
        )
    else:
        try:
            tailnet = valid_ip(tailnet, "TAILNET_IP")
        except ScriptError as exc:
            print(f"Invalid existing value: {exc}")
            tailnet = prompt(
                TAILNET_PROMPT,
                tailnet,
                validator=lambda value: valid_ip(value, "TAILNET_IP"),
            )
        if detected_tailnet and tailnet != detected_tailnet:
            print(
                f"Detected Tailscale address {detected_tailnet}, but TAILNET_IP is {tailnet}."
            )
            if confirm("Update TAILNET_IP to the detected address?", True):
                tailnet = detected_tailnet
                print(
                    "Afterward, update the Tailscale split-DNS nameserver if the address changed."
                )
    if traefik.set("TAILNET_IP", tailnet):
        changes.append("TAILNET_IP")

    public_bind = traefik.get("PUBLIC_BIND")
    detected_public_bind = detect_public_bind()
    if not public_bind:
        public_bind = detected_public_bind
    if not public_bind:
        public_bind = prompt(
            PUBLIC_BIND_PROMPT, validator=lambda value: valid_ip(value, "PUBLIC_BIND")
        )
    else:
        try:
            public_bind = valid_ip(public_bind, "PUBLIC_BIND")
        except ScriptError as exc:
            print(f"Invalid existing value: {exc}")
            public_bind = prompt(
                PUBLIC_BIND_PROMPT,
                public_bind,
                validator=lambda value: valid_ip(value, "PUBLIC_BIND"),
            )
        if detected_public_bind and public_bind != detected_public_bind:
            print(
                f"Detected public bind address {detected_public_bind}, but PUBLIC_BIND is {public_bind}."
            )
            if confirm("Update PUBLIC_BIND to the detected address?", False):
                public_bind = detected_public_bind
    if traefik.set("PUBLIC_BIND", public_bind):
        changes.append("PUBLIC_BIND")

    if not traefik.get("CROWDSEC_BOUNCER_API_KEY"):
        traefik.set("CROWDSEC_BOUNCER_API_KEY", secrets.token_hex(32))
        changes.append("CROWDSEC_BOUNCER_API_KEY")

    for key, default in (("SUB_DOMAIN_TRAEFIK", "traefik"),):
        value = validate_subdomain(traefik.get(key) or default, key)
        if traefik.set(key, value):
            changes.append(key)
    for app in (
        "jellyfin",
        "seerr",
        "radarr",
        "sonarr",
        "prowlarr",
        "bazarr",
        "infinidysk",
    ):
        key = f"SUB_DOMAIN_{app.upper()}"
        value = validate_subdomain(media.get(key) or app, key)
        if media.set(key, value):
            changes.append(key)

    detected_uid, detected_gid = detected_ids()
    configured_uid = media.get("ENV_PUID")
    configured_gid = media.get("ENV_PGID")
    uid = valid_id(configured_uid, "ENV_PUID") if configured_uid else detected_uid
    gid = valid_id(configured_gid, "ENV_PGID") if configured_gid else detected_gid
    if configured_uid and configured_gid and (uid, gid) != (detected_uid, detected_gid):
        print(
            f"Configured container identity: {uid}:{gid}\n"
            f"Current user identity:        {detected_uid}:{detected_gid}\n"
            "Keeping the configured identity is usually correct for an existing install.\n"
            "See the service setup guide for container ownership details."
        )
        if force and confirm(
            "Replace the configured container identity with the current user?", False
        ):
            uid, gid = detected_uid, detected_gid
            print(
                "warning: run just prepare after changing container ownership settings"
            )
    if media.set("ENV_PUID", uid):
        changes.append("ENV_PUID")
    if media.set("ENV_PGID", gid):
        changes.append("ENV_PGID")

    configure_infinidysk(media, force, changes)

    if force or not traefik.get("TRAEFIK_DASHBOARD_CREDENTIALS"):
        if confirm(
            "Configure the Traefik dashboard credentials?",
            bool(traefik.get("TRAEFIK_DASHBOARD_CREDENTIALS")),
        ):
            user = prompt(
                DASHBOARD_USER_PROMPT,
                default="admin",
                validator=lambda value: validate_subdomain(value, "dashboard username"),
            )
            password = prompt(DASHBOARD_PASSWORD_PROMPT, secret=True)
            if password:
                traefik.set(
                    "TRAEFIK_DASHBOARD_CREDENTIALS",
                    hash_dashboard_password(user, password),
                )
                changes.append("TRAEFIK_DASHBOARD_CREDENTIALS")

    if not traefik.get("CLOUDFLARE_DNS_TOKEN") or force:
        token = prompt(CLOUDFLARE_PROMPT, secret=True)
        if token:
            if not verify_cloudflare(token):
                raise ScriptError("Cloudflare token could not be verified as active")
            traefik.set("CLOUDFLARE_DNS_TOKEN", token)
            changes.append("CLOUDFLARE_DNS_TOKEN")

    if not restic.get("RESTIC_REPOSITORY") or not restic.get("RESTIC_PASSWORD"):
        if confirm("Configure Cloudflare R2 restic backups now?", False):
            account = prompt(R2_ACCOUNT_PROMPT, restic.get("R2_ACCOUNT_ID"))
            bucket = prompt(R2_BUCKET_PROMPT, restic.get("R2_BUCKET"))
            access = prompt(R2_ACCESS_PROMPT, restic.get("AWS_ACCESS_KEY_ID"))
            secret = prompt(R2_SECRET_PROMPT, secret=True)
            password = prompt(RESTIC_PASSWORD_PROMPT, secret=True)
            if secret:
                restic.set("AWS_SECRET_ACCESS_KEY", secret)
            if password:
                restic.set("RESTIC_PASSWORD", password)
            restic.set("R2_ACCOUNT_ID", account)
            restic.set("R2_BUCKET", bucket)
            restic.set("AWS_ACCESS_KEY_ID", access)
            restic.set("AWS_DEFAULT_REGION", "auto")
            restic.set(
                "RESTIC_REPOSITORY",
                f"s3:https://{account}.r2.cloudflarestorage.com/{bucket}",
            )
            restic.write()
            changes.append("restic configuration")

    traefik.write()
    media.write()
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and configure stack environment files"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-prompt optional secrets"
    )
    args = parser.parse_args()
    try:
        print(
            "kickstArrt setup\n"
            "  Private stack environment files will be created or updated.\n"
            "  Enter ? at any prompt for help.\n"
            "  Docs: docs/quickstart.md | docs/services/traefik.md | docs/maintenance.md\n"
        )
        changes = configure_env(args.force)
        print(f"init complete; updated {len(changes)} value(s).")
        print("Review stacks/*/.env, then run: just validate && just up")
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
