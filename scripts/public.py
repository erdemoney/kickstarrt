#!/usr/bin/env python3
"""Manage which services have a public Traefik router."""

from __future__ import annotations

import argparse

from .common import EnvFile, ROOT, ScriptError, run


MEDIA_ENV = ROOT / "stacks" / "media-server" / ".env"
COMPOSE = ROOT / "stacks" / "media-server" / "compose.yaml"

# Keep this list explicit: enabling a public router is an intentional exposure,
# not something that should happen for an arbitrary Compose service by accident.
SERVICES = {
    "jellyfin": "JELLYFIN_ENTRYPOINTS",
    "seerr": "SEERR_ENTRYPOINTS",
    "radarr": "RADARR_ENTRYPOINTS",
    "sonarr": "SONARR_ENTRYPOINTS",
    "prowlarr": "PROWLARR_ENTRYPOINTS",
    "bazarr": "BAZARR_ENTRYPOINTS",
    "infinidysk": "INFINIDYSK_ENTRYPOINTS",
}
PUBLIC_ENTRYPOINTS = "https,https-tailnet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="enable or disable public Traefik routers without editing Compose files"
    )
    parser.add_argument("action", choices=("enable", "disable", "status"))
    parser.add_argument("services", nargs="*", metavar="SERVICE")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without editing .env or recreating services",
    )
    return parser.parse_args()


def validate_services(names: list[str]) -> None:
    unknown = sorted(set(names) - set(SERVICES))
    if unknown:
        available = ", ".join(SERVICES)
        raise ScriptError(
            f"unknown service(s): {', '.join(unknown)}; available services: {available}"
        )


def status(env: EnvFile) -> int:
    for service, key in SERVICES.items():
        entrypoints = env.get(key, "https-tailnet")
        public = "https" in {item.strip() for item in entrypoints.split(",")}
        print(f"{service}: {'public + tailnet' if public else 'tailnet-only'}")
    return 0


def main() -> int:
    args = parse_args()
    env = EnvFile(MEDIA_ENV)

    if args.action == "status":
        if args.services:
            raise ScriptError("status does not accept service names")
        if args.dry_run:
            raise ScriptError("--dry-run only applies to enable or disable")
        return status(env)

    if not args.services:
        raise ScriptError(f"{args.action} requires at least one service name")
    validate_services(args.services)

    services = list(dict.fromkeys(args.services))
    would_change = False
    for service in services:
        key = SERVICES[service]
        target = PUBLIC_ENTRYPOINTS if args.action == "enable" else "https-tailnet"
        if env.get(key, "https-tailnet") == target:
            continue
        would_change = True
        if args.action == "enable":
            if args.dry_run:
                print(f"{service}: would enable the public + tailnet router")
            else:
                env.set(key, PUBLIC_ENTRYPOINTS)
                print(f"{service}: public + tailnet router enabled")
        else:
            if args.dry_run:
                print(f"{service}: would disable the public router (tailnet-only)")
            else:
                env.unset(key)
                print(f"{service}: tailnet-only router enabled")

    if would_change:
        if args.dry_run:
            print(
                f"would recreate: docker compose -f {COMPOSE} up -d {' '.join(services)}"
            )
        else:
            env.write()
            run(
                ("docker", "compose", "-f", str(COMPOSE), "up", "-d", *services),
                "recreate public service routers",
            )
    else:
        print("no configuration changes")
    print("UFW and DNS are unchanged; manage them separately.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScriptError as exc:
        raise SystemExit(f"error: {exc}")
