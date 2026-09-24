#!/usr/bin/env python3
"""Search Sonarr and Radarr for missing media and quality upgrades.

Run with no arguments inside the hunt container to execute a search. On the host,
`just hunt-run` (and the optional systemd timer) launch that container via the
`run` operation; `schedule`/`status`/`unschedule` manage the timer.
"""

from __future__ import annotations

import fcntl
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_CALENDAR = "*-*-* 03:00:00"
SERVICE_NAME = "kickstarrt-hunt"
SERVICE_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.service"
TIMER_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.timer"


class HuntError(RuntimeError):
    pass


def boolean(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, str(default)).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise HuntError(f"{name} must be true or false")
    return value in {"true", "1", "yes"}


def integer(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise HuntError(f"{name} must be an integer") from exc
    if value < minimum:
        raise HuntError(f"{name} must be at least {minimum}")
    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ArrAPI:
    def __init__(self, name: str, url: str, key: str):
        self.name = name
        self.base = url.rstrip("/")
        self.key = key

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base}/{path.lstrip('/')}",
            data=data,
            method=method,
            headers={"X-Api-Key": self.key, "Accept": "application/json"},
        )
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise HuntError(f"{self.name} request failed: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HuntError(f"{self.name} returned invalid JSON") from exc


def quality_ranks(profiles: list[dict[str, Any]]) -> dict[int, tuple[int, int]]:
    """Return profile/quality ranks, where a larger rank is better."""
    result: dict[int, tuple[int, int]] = {}
    for profile in profiles:
        flattened: list[int] = []

        def visit(items: list[dict[str, Any]]) -> None:
            for item in items:
                quality = item.get("quality") or {}
                if quality.get("id") is not None:
                    flattened.append(int(quality["id"]))
                visit(item.get("items") or [])

        visit(profile.get("items") or [])
        for rank, quality_id in enumerate(flattened):
            result[(int(profile["id"]), quality_id)] = (rank, len(flattened))
    return result


def quality_cutoffs(profiles: list[dict[str, Any]]) -> dict[int, int]:
    result: dict[int, int] = {}
    for profile in profiles:
        cutoff = profile.get("cutoff")
        cutoff_id = cutoff.get("id") if isinstance(cutoff, dict) else cutoff
        if cutoff_id is not None:
            result[int(profile["id"])] = int(cutoff_id)
    return result


def below_cutoff(item: dict[str, Any], ranks: dict[int, tuple[int, int]]) -> bool:
    if item.get("qualityCutoffNotMet") is not None:
        return bool(item["qualityCutoffNotMet"])
    profile_id = item.get("qualityProfileId")
    media_file = item.get("movieFile") or item.get("episodeFile") or {}
    quality = media_file.get("quality") or {}
    quality_id = (quality.get("quality") or {}).get("id")
    cutoff = item.get("qualityCutoff")
    if profile_id is None or quality_id is None or cutoff is None:
        return False
    current = ranks.get((int(profile_id), int(quality_id)))
    target = ranks.get((int(profile_id), int(cutoff)))
    return current is not None and target is not None and current[0] < target[0]


@dataclass
class Candidate:
    app: str
    kind: str
    item_id: int
    title: str

    @property
    def key(self) -> str:
        return f"{self.app}:{self.kind}:{self.item_id}"


def sonarr_candidates(api: ArrAPI, mode: str) -> list[Candidate]:
    series = api.request("GET", "series")
    profile_data = api.request("GET", "qualityprofile")
    profiles = quality_ranks(profile_data)
    cutoffs = quality_cutoffs(profile_data)
    candidates: list[Candidate] = []
    for show in series:
        if not show.get("monitored"):
            continue
        episodes = api.request("GET", f"episode?seriesId={show['id']}")
        for episode in episodes:
            if not episode.get("monitored") or episode.get("seasonNumber", 0) == 0:
                continue
            missing = not episode.get("hasFile", False)
            upgrade = not missing and below_cutoff(
                {
                    **episode,
                    "qualityProfileId": show.get("qualityProfileId"),
                    "qualityCutoff": cutoffs.get(show.get("qualityProfileId")),
                },
                profiles,
            )
            # Sonarr's episode resource commonly exposes the cutoff flag only on
            # newer releases. The command-level fallback handles older releases.
            if mode in {"missing", "both"} and missing:
                candidates.append(
                    Candidate(
                        "sonarr",
                        "missing",
                        int(episode["id"]),
                        f"{show['title']} - {episode['title']}",
                    )
                )
            elif mode in {"upgrades", "both"} and upgrade:
                candidates.append(
                    Candidate(
                        "sonarr",
                        "upgrade",
                        int(episode["id"]),
                        f"{show['title']} - {episode['title']}",
                    )
                )
    return candidates


def radarr_candidates(api: ArrAPI, mode: str) -> list[Candidate]:
    movies = api.request("GET", "movie")
    profiles = quality_ranks(api.request("GET", "qualityprofile"))
    candidates: list[Candidate] = []
    for movie in movies:
        if not movie.get("monitored"):
            continue
        missing = not movie.get("hasFile", False)
        upgrade = not missing and below_cutoff(movie, profiles)
        if mode in {"missing", "both"} and missing:
            candidates.append(
                Candidate("radarr", "missing", int(movie["id"]), movie["title"])
            )
        elif mode in {"upgrades", "both"} and upgrade:
            candidates.append(
                Candidate("radarr", "upgrade", int(movie["id"]), movie["title"])
            )
    return candidates


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HuntError(f"cannot read state file {path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(state, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise HuntError(f"cannot write state file {path}: {exc}") from exc


def chunks(items: list[Candidate], size: int) -> list[list[Candidate]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def hunt() -> None:
    mode = os.environ.get("HUNT_MODE", "both").strip().lower()
    if mode not in {"missing", "upgrades", "both"}:
        raise HuntError("HUNT_MODE must be missing, upgrades, or both")
    state_path = Path(os.environ.get("HUNT_STATE_FILE", "/state/state.json"))
    cooldown = timedelta(days=integer("HUNT_COOLDOWN_DAYS", 7))
    delay = integer("HUNT_DELAY_SECONDS", 60)
    max_items = integer("HUNT_MAX_ITEMS_PER_RUN", 100, 1)
    max_queue = integer("HUNT_MAX_QUEUE_SIZE", 0)
    missing_batch = integer("HUNT_MISSING_BATCH_SIZE", 10, 1)
    upgrade_batch = integer("HUNT_UPGRADE_BATCH_SIZE", 5, 1)
    state = load_state(state_path)
    cutoff = utc_now() - cooldown
    state = {key: value for key, value in state.items() if parse_time(value) >= cutoff}

    services: list[tuple[ArrAPI, list[Candidate]]] = []
    if boolean("HUNT_SONARR", True) and os.environ.get("HUNT_SONARR_API_KEY"):
        api = ArrAPI(
            "Sonarr",
            os.environ.get("HUNT_SONARR_URL", "http://sonarr:8989/api/v3"),
            os.environ["HUNT_SONARR_API_KEY"],
        )
        services.append((api, sonarr_candidates(api, mode)))
    if boolean("HUNT_RADARR", True) and os.environ.get("HUNT_RADARR_API_KEY"):
        api = ArrAPI(
            "Radarr",
            os.environ.get("HUNT_RADARR_URL", "http://radarr:7878/api/v3"),
            os.environ["HUNT_RADARR_API_KEY"],
        )
        services.append((api, radarr_candidates(api, mode)))
    if not services:
        raise HuntError("no enabled service has an API key configured")

    candidates = [
        candidate
        for _, found in services
        for candidate in found
        if candidate.key not in state
    ]
    candidates = sorted(
        candidates,
        key=lambda candidate: (
            candidate.kind != "missing",
            candidate.app,
            candidate.title,
        ),
    )[:max_items]
    apis = {api.name.lower(): api for api, _ in services}
    submitted = 0
    for kind in ("missing", "upgrade"):
        selected = [candidate for candidate in candidates if candidate.kind == kind]
        batch_size = missing_batch if kind == "missing" else upgrade_batch
        for batch in chunks(selected, batch_size):
            by_app: dict[str, list[Candidate]] = {}
            for candidate in batch:
                by_app.setdefault(candidate.app, []).append(candidate)
            for app, app_batch in by_app.items():
                api = apis[app]
                if max_queue:
                    queue = api.request("GET", "queue?page=1&pageSize=1") or {}
                    queued = int(queue.get("totalRecords", 0))
                    if queued >= max_queue:
                        print(
                            f"{api.name}: queue has {queued} item(s); pausing this app"
                        )
                        continue
                command = "EpisodeSearch" if app == "sonarr" else "MoviesSearch"
                id_key = "episodeIds" if app == "sonarr" else "movieIds"
                api.request(
                    "POST",
                    "command",
                    {"name": command, id_key: [item.item_id for item in app_batch]},
                )
                timestamp = iso_now()
                for item in app_batch:
                    state[item.key] = timestamp
                save_state(state_path, state)
                submitted += len(app_batch)
                print(
                    f"{api.name}: submitted {kind} search for {len(app_batch)} item(s)"
                )
                if delay and (submitted < len(candidates)):
                    time.sleep(delay)
    print(
        f"submitted {submitted} search item(s); skipped {len(candidates) - submitted} item(s) due to limits/cooldown"
    )


def run_worker() -> int:
    lock_path = Path(os.environ.get("HUNT_LOCK_FILE", "/tmp/hunt.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HuntError("another hunt run is already in progress") from exc
        hunt()
    return 0


def require_just() -> str:
    from .common import ScriptError

    just = shutil.which("just")
    if just is None:
        raise ScriptError("'just' not on PATH - install just before scheduling")
    return just


def run_container(mode: str) -> None:
    from .common import EnvFile, ROOT, ScriptError, run

    if mode not in {"missing", "upgrades", "both"}:
        raise ScriptError("HUNT_MODE must be missing, upgrades, or both")
    env = ROOT / "stacks" / "media-server" / ".env"
    if not env.is_file():
        raise ScriptError("no stacks/media-server/.env - run 'just init' first")
    state = ROOT / "data" / "hunt"
    state.mkdir(parents=True, exist_ok=True)
    config = EnvFile(env)
    image = os.environ.get("HUNT_IMAGE", "python:3.13-alpine3.22")
    puid = config.get("ENV_PUID") or "1000"
    pgid = config.get("ENV_PGID") or "1000"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "internal",
        "--user",
        f"{puid}:{pgid}",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-v",
        f"{ROOT / 'scripts' / 'hunt.py'}:/app/hunt.py:ro",
        "-v",
        f"{state}:/state",
        "--workdir",
        "/app",
        "-e",
        f"HUNT_MODE={mode}",
    ]
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("HUNT_") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        if value:
            command.extend(["-e", f"{key}={value}"])
    command.extend([image, "python", "/app/hunt.py"])
    run(command, f"hunt run ({mode})")


def write_unit(path: str, content: str) -> None:
    from .common import ScriptError

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
    from .common import ROOT, ScriptError, run

    if shutil.which("systemctl") is None:
        raise ScriptError(
            "systemd is unavailable; run 'just hunt-run' manually instead"
        )
    if shutil.which("sudo") is None:
        raise ScriptError("sudo not found - install sudo before scheduling")
    just = require_just()
    if "\n" in calendar or "\r" in calendar or "\x00" in calendar:
        raise ScriptError("invalid newline or NUL in calendar")
    if shutil.which("systemd-analyze") is not None:
        run(("systemd-analyze", "calendar", calendar), "validate hunt calendar")

    user = getpass.getuser()
    print(
        "Hunt timer\n"
        f"  Command : {just} hunt-run\n"
        f"  Workdir : {ROOT}\n"
        f"  Schedule: {calendar} (local server time)\n"
        f"  User    : {user}\n"
        "  Behavior: no catch-up; runs cannot overlap (in-container lock)\n"
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
            "Description=Search Sonarr and Radarr back catalogs",
            "After=network-online.target docker.service",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"User={user}",
            f"WorkingDirectory={ROOT}",
            f"ExecStart={just} hunt-run",
            "",
        ]
    )
    timer = "\n".join(
        [
            "[Unit]",
            "Description=Run the Sonarr/Radarr back-catalog hunt",
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
    print(f"\ninstalled {SERVICE_NAME}.{{service,timer}} - timer enabled and active")
    status()
    print("remove it later with 'just hunt-unschedule'.")


def status() -> None:
    from .common import ScriptError, run

    if shutil.which("systemctl") is None:
        raise ScriptError("systemd is unavailable")
    run(
        ("systemctl", "list-timers", f"{SERVICE_NAME}.timer", "--no-pager"),
        "list hunt timer",
    )


def unschedule() -> None:
    from .common import ScriptError, run

    if shutil.which("systemctl") is None:
        print("no systemd - nothing to uninstall")
        return
    if shutil.which("sudo") is None:
        raise ScriptError("sudo not found - run these commands as root")
    subprocess.run(
        ["sudo", "systemctl", "disable", "--now", f"{SERVICE_NAME}.timer"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["sudo", "systemctl", "reset-failed", f"{SERVICE_NAME}.timer"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run(("sudo", "rm", "-f", TIMER_UNIT, SERVICE_UNIT), "remove hunt units")
    run(("sudo", "systemctl", "daemon-reload"), "reload systemd")
    print(f"removed {SERVICE_NAME}.{{timer,service}} and stopped the timer.")


def main(argv: list[str]) -> int:
    if not argv:
        return run_worker()

    from .common import ScriptError

    operation = argv[0]
    try:
        if operation == "run":
            run_container(argv[1] if len(argv) > 1 else "both")
        elif operation == "schedule":
            schedule(argv[1] if len(argv) > 1 else DEFAULT_CALENDAR)
        elif operation == "status":
            status()
        elif operation == "unschedule":
            unschedule()
        else:
            raise ScriptError(f"unknown hunt operation: {operation}")
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except HuntError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
