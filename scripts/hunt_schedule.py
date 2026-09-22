#!/usr/bin/env python3
"""Install and manage the ephemeral media-hunt systemd timer."""

from __future__ import annotations

import getpass
import shutil
import subprocess
import sys

from .common import ROOT, ScriptError, run


SERVICE_NAME = "kickstarrt-hunt"
SERVICE_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.service"
TIMER_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.timer"
COMPOSE = ROOT / "stacks" / "media-server" / "compose.yaml"


def write_unit(path: str, content: str) -> None:
    result = subprocess.run(
        ["sudo", "tee", path],
        input=content,
        text=True,
        stdout=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        raise ScriptError(f"could not write {path}")


def schedule(calendar: str) -> None:
    if shutil.which("systemctl") is None or shutil.which("sudo") is None:
        raise ScriptError("systemd and sudo are required to schedule hunts")
    if any(character in calendar for character in "\n\r\x00"):
        raise ScriptError("invalid newline or NUL in calendar")
    if shutil.which("systemd-analyze"):
        run(("systemd-analyze", "calendar", calendar), "validate hunt calendar")
    user = getpass.getuser()
    print(f"Schedule: {calendar}\nCommand: docker compose run --rm --no-deps hunt")
    try:
        confirmation = input("Proceed? [y/N] ")
    except EOFError:
        confirmation = ""
    if confirmation.lower() not in {"y", "yes"}:
        raise ScriptError("aborted")
    service = "\n".join(
        [
            "[Unit]",
            "Description=Search Sonarr and Radarr back catalogs",
            "After=network-online.target docker.service",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"User={user}",
            f"WorkingDirectory={ROOT}",
            f"ExecStart=/usr/bin/docker compose -f {COMPOSE} run --build --rm --no-deps hunt",
            "",
        ]
    )
    timer = "\n".join(
        [
            "[Unit]",
            "Description=Search Sonarr and Radarr back catalogs",
            "",
            "[Timer]",
            f"OnCalendar={calendar}",
            "Persistent=false",
            f"Unit={SERVICE_NAME}.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )
    write_unit(SERVICE_UNIT, service)
    write_unit(TIMER_UNIT, timer)
    run(("sudo", "systemctl", "daemon-reload"), "reload systemd")
    run(
        ("sudo", "systemctl", "enable", "--now", f"{SERVICE_NAME}.timer"),
        "enable hunt timer",
    )


def main(argv: list[str]) -> int:
    operation = argv[0] if argv else "run"
    if operation == "schedule":
        schedule(argv[1] if len(argv) > 1 else "*-*-* 03:00:00")
    elif operation == "status":
        run(
            ("systemctl", "list-timers", f"{SERVICE_NAME}.timer", "--no-pager"),
            "list hunt timer",
        )
    elif operation == "unschedule":
        run(
            ("sudo", "systemctl", "disable", "--now", f"{SERVICE_NAME}.timer"),
            "disable hunt timer",
        )
        run(("sudo", "rm", "-f", TIMER_UNIT, SERVICE_UNIT), "remove hunt units")
        run(("sudo", "systemctl", "daemon-reload"), "reload systemd")
    else:
        raise ScriptError(f"unknown operation: {operation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
