#!/usr/bin/env python3
"""Run the repository's restic backup operations in a container."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from .common import ROOT, ScriptError, run


IMAGE = os.environ.get("RESTIC_IMAGE", "restic/restic:0.19.1")
ENV_FILE = ROOT / ".env.restic"
CACHE_VOLUME = "restic-cache:/root/.cache/restic"
SERVICE_UNIT = "/etc/systemd/system/kickstarrt-restic-backup.service"
TIMER_UNIT = "/etc/systemd/system/kickstarrt-restic-backup.timer"


def env_value(key: str) -> str:
    if not ENV_FILE.is_file():
        raise ScriptError("no .env.restic - configure restic first")
    prefix = f"{key}="
    value = ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            value = line.split("=", 1)[1].strip()
    return value.strip("'\"")


def require_config() -> None:
    env_value("RESTIC_REPOSITORY")
    env_value("RESTIC_PASSWORD")


def restic(*args: str, repo_mount: str | None = None, read_only: bool = False) -> None:
    command = [
        "docker",
        "run",
        "--rm",
        "--env-file",
        str(ENV_FILE),
        "-v",
        "/etc/localtime:/etc/localtime:ro",
        "-v",
        CACHE_VOLUME,
    ]
    if repo_mount:
        suffix = ":/repo:ro" if read_only else ":/repo"
        command.extend(["-v", f"{repo_mount}{suffix}"])
    command.extend([IMAGE, *args])
    run(command, f"restic {' '.join(args)}")


def repository_initialized() -> bool:
    command = [
        "docker",
        "run",
        "--rm",
        "--env-file",
        str(ENV_FILE),
        "-v",
        "/etc/localtime:/etc/localtime:ro",
        "-v",
        CACHE_VOLUME,
        IMAGE,
        "snapshots",
    ]
    try:
        result = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
    except OSError:
        return False
    return result.returncode == 0


def backup_init() -> None:
    require_config()
    repository = env_value("RESTIC_REPOSITORY")
    if repository_initialized():
        print(f"repository already initialized at {repository}")
        return
    print("initializing restic repository ...")
    restic("init")


def backup() -> None:
    require_config()
    restic("backup", "/repo", repo_mount=str(ROOT), read_only=True)


def backup_list() -> None:
    require_config()
    restic("snapshots")


def backup_check() -> None:
    require_config()
    restic("check")


def backup_prune() -> None:
    require_config()
    keep_args: list[str] = []
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"RESTIC_KEEP_([A-Z]+)=([0-9]+)", line)
        if match and int(match.group(2)) > 0:
            keep_args.extend([f"--keep-{match.group(1).lower()}", match.group(2)])
    restic("forget", "--prune", *keep_args)


def backup_restore(snapshot: str) -> None:
    require_config()
    print("previewing what the restore would change (dry run; nothing is written) ...")
    restic(
        "restore",
        snapshot,
        "--target",
        "/",
        "--dry-run",
        "-vv",
        repo_mount=str(ROOT),
        read_only=True,
    )
    print()
    print(
        f"Files not in the snapshot are kept; the rest get overwritten in place. Restore {snapshot} into {ROOT}/? ",
        end="",
        flush=True,
    )
    try:
        confirmation = input()
    except EOFError:
        confirmation = ""
    if confirmation.lower() not in {"y", "yes"}:
        print("aborted - nothing was restored.")
        raise ScriptError("restore aborted")
    print()
    print(f"restoring {snapshot} into {ROOT}/ ...")
    restic("restore", snapshot, "--target", "/", repo_mount=str(ROOT))


def write_unit(path: str, content: str) -> None:
    try:
        result = subprocess.run(
            ["sudo", "tee", path],
            input=content,
            text=True,
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        raise ScriptError(f"could not write {path}: {exc}") from exc
    if result.returncode:
        raise ScriptError(f"could not write {path}")


def backup_schedule(calendar: str) -> None:
    if shutil.which("systemctl") is None:
        print(
            "no systemd (systemctl not found) - run the backup via cron instead, e.g.:"
        )
        print(
            f"  0 4 * * * cd '{ROOT}' && $(command -v just || echo 'just') backup && $(command -v just || echo 'just') backup-prune"
        )
        print("(or your NAS scheduler; see docs/maintenance.md)")
        raise ScriptError("systemd is unavailable")
    if shutil.which("sudo") is None:
        raise ScriptError("sudo not found - install sudo or run these commands as root")
    if shutil.which("just") is None:
        raise ScriptError("'just' not on PATH - install just before scheduling")
    require_config()

    just_bin = shutil.which("just")
    print(
        "Backup timer\n"
        f"  Command : {just_bin} backup && {just_bin} backup-prune\n"
        f"  Workdir : {ROOT}\n"
        f"  Schedule: {calendar}\n"
        "  Behavior: prune runs only after a successful backup\n"
        f"  Units   : {TIMER_UNIT}\n"
        f"            {SERVICE_UNIT}"
    )
    try:
        confirmation = input("Proceed? [y/N] ")
    except EOFError:
        confirmation = ""
    if confirmation.lower() not in {"y", "yes"}:
        raise ScriptError("aborted")

    service = "\n".join(
        [
            "[Unit]",
            "Description=Restic backup of the media repo",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={ROOT}",
            f"ExecStart={just_bin} backup",
            f"ExecStart={just_bin} backup-prune",
            "",
        ]
    )
    timer = "\n".join(
        [
            "[Unit]",
            "Description=Run the restic repo backup daily",
            "",
            "[Timer]",
            f"OnCalendar={calendar}",
            "Persistent=true",
            "Unit=kickstarrt-restic-backup.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )
    write_unit(SERVICE_UNIT, service)
    write_unit(TIMER_UNIT, timer)
    run(["sudo", "systemctl", "daemon-reload"], "reload systemd")
    run(
        ["sudo", "systemctl", "enable", "--now", "kickstarrt-restic-backup.timer"],
        "enable backup timer",
    )
    print(
        "\ninstalled kickstarrt-restic-backup.{service,timer} - timer enabled and active; each run backs up then prunes."
    )
    run(
        ["systemctl", "list-timers", "kickstarrt-restic-backup.timer", "--no-pager"],
        "list backup timer",
    )
    print("remove it later with 'just backup-unschedule'.")


def backup_unschedule() -> None:
    if shutil.which("systemctl") is None:
        print("no systemd - nothing to uninstall")
        return
    if shutil.which("sudo") is None:
        raise ScriptError("sudo not found - run these commands as root")
    subprocess.run(
        ["sudo", "systemctl", "disable", "--now", "kickstarrt-restic-backup.timer"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["sudo", "systemctl", "reset-failed", "kickstarrt-restic-backup.timer"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run(["sudo", "rm", "-f", TIMER_UNIT, SERVICE_UNIT], "remove backup units")
    run(["sudo", "systemctl", "daemon-reload"], "reload systemd")
    print("removed kickstarrt-restic-backup.{timer,service} and stopped the timer.")


def main(argv: list[str]) -> int:
    if not argv:
        raise ScriptError("missing backup operation")
    operation = argv[0]
    if operation == "init":
        backup_init()
    elif operation == "backup":
        backup()
    elif operation == "list":
        backup_list()
    elif operation == "check":
        backup_check()
    elif operation == "prune":
        backup_prune()
    elif operation == "restore":
        backup_restore(argv[1] if len(argv) > 1 else "latest")
    elif operation == "schedule":
        backup_schedule(argv[1] if len(argv) > 1 else "daily")
    elif operation == "unschedule":
        backup_unschedule()
    else:
        raise ScriptError(f"unknown backup operation: {operation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
