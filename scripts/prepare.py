#!/usr/bin/env python3
"""Prepare runtime directories and host settings consumed by Compose."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .common import (
    EnvFile,
    ROOT,
    ScriptError,
    capture,
    detect_public_ipv4,
    detect_tailscale_ipv4,
    run,
)


MEDIA_ENV = ROOT / "stacks" / "media-server" / ".env"
TRAEFIK_ENV = ROOT / "stacks" / "traefik" / ".env"


def value(env: EnvFile, key: str, default: str = "") -> str:
    return env.get(key, default)


def detect_tailscale() -> str:
    return detect_tailscale_ipv4()


def detect_public_bind() -> str:
    return detect_public_ipv4()


def configured_ids(media: EnvFile) -> tuple[int, int]:
    uid = media.get("ENV_PUID")
    gid = media.get("ENV_PGID")
    try:
        puid = int(uid) if uid else (os.getuid() or 1000)
        pgid = int(gid) if gid else (os.getgid() or 1000)
    except ValueError as exc:
        raise ScriptError("ENV_PUID and ENV_PGID must be numeric") from exc
    if os.getuid() == 0 and not uid:
        puid = 1000
    if os.getgid() == 0 and not gid:
        pgid = 1000
    if not 0 <= puid <= 65535 or not 0 <= pgid <= 65535:
        raise ScriptError("ENV_PUID and ENV_PGID must be between 0 and 65535")
    return puid, pgid


def ensure_owned(paths: list[Path], puid: int, pgid: int) -> None:
    missing_or_wrong = []
    for path in paths:
        try:
            if (
                Path(capture(("findmnt", "-rno", "TARGET", str(path)), "mount check"))
                == path
            ):
                continue
        except ScriptError:
            pass
        try:
            stat = path.stat()
        except FileNotFoundError:
            missing_or_wrong.append(path)
            continue
        if (stat.st_uid, stat.st_gid) != (puid, pgid):
            missing_or_wrong.append(path)
    if not missing_or_wrong:
        return
    if os.geteuid() == 0:
        for path in missing_or_wrong:
            path.mkdir(parents=True, exist_ok=True)
            os.chown(path, puid, pgid)
        return
    if shutil.which("sudo") is None:
        print(
            "warning: no root or sudo available; cannot prepare /mnt/debrid",
            file=sys.stderr,
        )
        return
    run(
        ("sudo", "mkdir", "-p", *[str(path) for path in missing_or_wrong]),
        "create media directories",
    )
    run(
        (
            "sudo",
            "chown",
            *[f"{puid}:{pgid}"] + [str(path) for path in missing_or_wrong],
        ),
        "own media directories",
    )


def main() -> int:
    try:
        media = EnvFile(MEDIA_ENV)
        traefik = EnvFile(TRAEFIK_ENV)
        config_dir = ROOT / "data"
        puid, pgid = configured_ids(media)

        ensure_owned(
            [
                Path("/mnt/debrid") / name
                for name in ("", "decypharr", "shows", "movies", "downloads")
            ],
            puid,
            pgid,
        )
        directories = (
            "jellyfin/config",
            "seerr/config",
            "radarr",
            "sonarr",
            "prowlarr",
            "recyclarr",
            "bazarr/config",
            "decypharr/configs",
            "comet",
            "comet-pg",
            "crowdsec/config",
            "crowdsec/data",
        )
        for directory in directories:
            (config_dir / directory).mkdir(parents=True, exist_ok=True)
        (config_dir / "traefik" / "logs").mkdir(parents=True, exist_ok=True)
        acme = config_dir / "traefik" / "acme.json"
        if acme.is_dir():
            raise ScriptError(
                f"{acme} must be a file, not a directory; remove it and rerun just prepare"
            )
        acme.touch(exist_ok=True)
        acme.chmod(0o600)

        changed = False
        for key, detector in (
            ("TAILNET_IP", detect_tailscale),
            ("PUBLIC_BIND", detect_public_bind),
        ):
            if not value(traefik, key):
                detected = detector()
                if detected:
                    traefik.set(key, detected)
                    changed = True
                    print(f"filled {key}={detected} in stacks/traefik/.env")
        if changed:
            traefik.write()
        try:
            os.chown(config_dir, puid, pgid)
        except OSError:
            pass
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
