#!/usr/bin/env python3
"""Interactively reconcile the stable, cross-service media wiring.

The script deliberately uses the applications' APIs instead of editing their
configuration files. HTTP is executed from a temporary container on the internal
Docker network so private service names (sonarr, radarr, etc.) remain usable.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from .common import EnvFile, ScriptError, read_arr_api_key
except ImportError:  # direct invocation via `python3 scripts/wire.py`
    from common import EnvFile, ScriptError, read_arr_api_key


ROOT = Path(__file__).resolve().parent.parent
MEDIA_ENV = ROOT / "stacks" / "media-server" / ".env"
MEDIA_COMPOSE = ROOT / "stacks" / "media-server" / "compose.yaml"
HTTP_IMAGE = "curlimages/curl:8.12.1"
HTTP_NETWORK = "internal"

SEERR_URL = "http://seerr:5055"
SEERR_JELLYFIN_HOST = "jellyfin"
SEERR_JELLYFIN_PORT = 8096
SEERR_JELLYFIN_SERVER_TYPE = 2  # MediaServerType.JELLYFIN
MAINTAINERR_URL = "http://maintainerr:6246"

# InfiniDysk Automatic queue management, as ArrConfig.QueueRule in the upstream
# backend. Rules match a completed/import-pending queue record's status messages
# by case-sensitive substring, and the strongest match wins, so a message may
# match more than one rule. Action is ArrConfig.QueueAction: 1 Remove,
# 2 RemoveAndBlocklist, 3 RemoveAndBlocklistAndSearch.
#
# Only reasons that are a property of the release itself are configured. Omitted
# reasons keep the upstream default of Do Nothing, which leaves the record in
# Awaiting import for an operator: releases matched by ID, archive layouts, and
# sample/season-numbering ambiguities can all be importable after a manual
# lookup, and blocklisting them would reject a usable release.
INFINIDYSK_QUEUE_RULES = [
    # Permanently unusable media: discard the release and ask for a replacement.
    {"Message": "Sample", "Action": 3},
    {"Message": "No audio tracks detected", "Action": 3},
    {"Message": "No files found are eligible for import", "Action": 3},
    {"Message": "Episode was not found in the grabbed release", "Action": 3},
    # A valid release that simply lost to what is already in the library. Drop
    # it and keep it out of future searches, but do not trigger another search.
    {"Message": "Not an upgrade for existing episode file", "Action": 2},
    {"Message": "Not an upgrade for existing movie file", "Action": 2},
    {"Message": "Not a Custom Format upgrade", "Action": 2},
    # Already in the library: clear the duplicate without recording the upload
    # as rejected, so InfiniDysk's re-grab protection stays out of the way.
    {"Message": "Episode file already imported", "Action": 1},
]


class WireError(RuntimeError):
    pass


class HTTPWireError(WireError):
    """An HTTP response with a client or server error status."""

    def __init__(self, source: str, method: str, url: str, status: int, text: str):
        self.source = source
        self.method = method
        self.url = url
        self.status = status
        super().__init__(f"{method} {url} returned HTTP {status}: {text.strip()[:300]}")


def api_key(app: str, config_dir: Path) -> str:
    try:
        return read_arr_api_key(app, config_dir)
    except ScriptError as exc:
        raise WireError(str(exc)) from exc


def bazarr_api_key(config_dir: Path) -> tuple[Path, str]:
    path = config_dir / "bazarr" / "config" / "config" / "config.yaml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise WireError(f"{path} does not exist; start Bazarr once first") from exc

    section = ""
    for line in lines:
        top_level = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if top_level:
            section = top_level.group(1)
            continue
        value = re.match(r"^\s+apikey:\s*(\S.*)\s*$", line)
        if section == "auth" and value:
            return path, value.group(1).strip("'\"")
    raise WireError(f"{path} does not contain Bazarr's API key")


def seerr_api_key(config_dir: Path) -> str:
    # Seerr stores its configuration in a JSON file; the generated management
    # API key authenticates every authenticated request below as the admin user.
    path = config_dir / "seerr" / "config" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WireError(f"{path} does not exist; start Seerr once first") from exc
    except json.JSONDecodeError as exc:
        raise WireError(f"cannot parse {path}: {exc}") from exc
    key = ((data.get("main") or {}).get("apiKey") or "").strip()
    if not key:
        raise WireError(f"{path} does not contain Seerr's API key")
    return key


def yaml_section_value(path: Path, section_name: str, key_name: str) -> str:
    """Read one scalar from Bazarr's simple top-level config sections."""
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        top_level = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if top_level:
            section = top_level.group(1)
            continue
        value = re.match(rf"^\s+{re.escape(key_name)}:\s*(\S.*)\s*$", line)
        if section == section_name and value:
            return value.group(1).strip("'\"")
    return ""


class DockerHTTP:
    """Run curl in a temporary internal-network container."""

    def __init__(self) -> None:
        self.container = f"kickstarrt-wire-{uuid.uuid4().hex}"

    def __enter__(self) -> DockerHTTP:
        run_command(
            [
                "docker",
                "run",
                "--detach",
                "--network",
                HTTP_NETWORK,
                "--name",
                self.container,
                "--entrypoint",
                "sleep",
                HTTP_IMAGE,
                "2147483647",
            ],
            "start temporary HTTP helper",
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            result = subprocess.run(
                ["docker", "rm", "--force", self.container],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as cleanup_error:
            detail = f"could not remove temporary HTTP helper: {cleanup_error}"
        else:
            if result.returncode == 0:
                return False
            detail = result.stderr.strip() or "docker rm failed"
            detail = f"could not remove temporary HTTP helper: {detail}"

        if exc_type is not None:
            print(f"warning: {detail}", file=sys.stderr)
            return False
        raise WireError(detail)

    def request(
        self,
        source: str,
        method: str,
        url: str,
        key: str | None = None,
        body: Any = None,
        auth_header: str = "X-Api-Key",
        form: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        command = [
            "docker",
            "exec",
            self.container,
            "curl",
            "-sS",
            "-X",
            method,
            "-w",
            "\n__WIRE_HTTP_STATUS__%{http_code}",
            url,
        ]
        if key:
            command.extend(["-H", f"{auth_header}: {key}"])
        for name, value in (headers or {}).items():
            command.extend(["-H", f"{name}: {value}"])
        if body is not None:
            command.extend(
                ["-H", "Content-Type: application/json", "--data", json.dumps(body)]
            )
        if form is not None:
            for name, value in form.items():
                values = value if isinstance(value, list) else [value]
                if not values:
                    values = [""]
                for item in values:
                    if isinstance(item, bool):
                        item = str(item).lower()
                    command.extend(["--data-urlencode", f"{name}={item}"])
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
        except OSError as exc:
            raise WireError(f"could not run Docker: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip() or "curl failed"
            raise WireError(f"{source} request failed: {detail}")
        marker = "\n__WIRE_HTTP_STATUS__"
        if marker not in result.stdout:
            raise WireError(f"{source} returned an invalid HTTP response")
        text, status = result.stdout.rsplit(marker, 1)
        if int(status) >= 400:
            raise HTTPWireError(source, method, url, int(status), text)
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise WireError(f"{method} {url} returned non-JSON data") from exc


def run_command(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise WireError(f"could not run {label}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise WireError(f"{label} failed: {detail[-500:]}")
    return result


@dataclass
class Change:
    service: str
    description: str
    details: list[str]
    apply: Callable[[], None]


def field_value(resource: dict[str, Any], name: str) -> Any:
    for field in resource.get("fields", []):
        if field.get("name") == name:
            return field.get("value")
    return None


def set_field(resource: dict[str, Any], name: str, value: Any) -> None:
    for field in resource.setdefault("fields", []):
        if field.get("name") == name:
            field["value"] = value
            return
    resource["fields"].append({"name": name, "value": value})


def remove_field(resource: dict[str, Any], name: str) -> None:
    resource["fields"] = [
        field for field in resource.get("fields", []) if field.get("name") != name
    ]


def redacted(value: Any, name: str = "") -> str:
    if any(word in name.lower() for word in ("key", "token", "password", "secret")):
        return "<unchanged secret>" if value else "<empty>"
    return str(value)


def arr_download_client(
    http: DockerHTTP,
    app: str,
    key: str,
    implementation: str,
    contract: str,
    name: str,
    fields: dict[str, Any],
) -> Change | None:
    current = http.request(
        app,
        "GET",
        f"http://{app}:{8989 if app == 'sonarr' else 7878}/api/v3/downloadclient",
        key,
    )
    existing = next((x for x in current if x.get("name") == name), None)
    desired_fields = dict(fields)
    desired_fields["tvCategory" if app == "sonarr" else "movieCategory"] = (
        "tv" if app == "sonarr" else "movies"
    )
    if existing:
        payload = json.loads(json.dumps(existing))
        changed = []
        if existing.get("enable") is not True:
            changed.append(f"enable: {existing.get('enable')} -> True")
            payload["enable"] = True
        for field, value in desired_fields.items():
            old = field_value(existing, field)
            if old != value:
                changed.append(
                    f"{field}: {redacted(old, field)} -> {redacted(value, field)}"
                )
                set_field(payload, field, value)
        if existing.get("implementation") != implementation:
            changed.append(
                f"implementation: {existing.get('implementation')} -> {implementation}"
            )
            payload["implementation"] = implementation
        secret_field = next(
            (
                field
                for field in ("apiKey", "password")
                if desired_fields.get(field)
                and field_value(existing, field) != desired_fields.get(field)
            ),
            None,
        )
        if secret_field:
            try:
                http.request(
                    app,
                    "POST",
                    f"http://{app}:{8989 if app == 'sonarr' else 7878}/api/v3/downloadclient/test?forceTest=true",
                    key,
                    payload,
                )
            except WireError:
                pass
            else:
                # The Arr API may mask stored credentials. A successful
                # candidate test proves the existing secret works, so preserve
                # it rather than rewriting a secret-only difference.
                remove_field(payload, secret_field)
                changed = [
                    item for item in changed if not item.startswith(f"{secret_field}:")
                ]
        if not changed:
            return None
        endpoint = f"http://{app}:{8989 if app == 'sonarr' else 7878}/api/v3/downloadclient/{existing['id']}"
        return Change(
            app,
            f"update {name}",
            changed,
            lambda: http.request(app, "PUT", endpoint, key, payload),
        )

    payload = {
        "name": name,
        "enable": True,
        "protocol": "usenet",
        "implementation": implementation,
        "implementationName": implementation,
        "configContract": contract,
        "fields": [
            {"name": field, "value": value} for field, value in desired_fields.items()
        ],
        "priority": 1,
    }
    endpoint = f"http://{app}:{8989 if app == 'sonarr' else 7878}/api/v3/downloadclient"
    return Change(
        app,
        f"create {name}",
        [
            f"{field}: {redacted(value, field)}"
            for field, value in desired_fields.items()
        ],
        lambda: http.request(app, "POST", endpoint, key, payload),
    )


def root_folder_change(
    http: DockerHTTP, app: str, key: str, path: str
) -> Change | None:
    port = 8989 if app == "sonarr" else 7878
    endpoint = f"http://{app}:{port}/api/v3/rootfolder"
    current = http.request(app, "GET", endpoint, key)
    if any(folder.get("path") == path for folder in current):
        return None
    return Change(
        app,
        f"create root folder {path}",
        [f"path: {path}"],
        lambda: http.request(app, "POST", endpoint, key, {"path": path}),
    )


def infinidysk_arr_settings_change(
    media_env: EnvFile, keys: dict[str, str]
) -> Change | None:
    """Keep InfiniDysk's headless Arr registrations aligned with the live apps."""
    desired = {
        "RadarrInstances": [{"Host": "http://radarr:7878", "ApiKey": keys["radarr"]}],
        "SonarrInstances": [{"Host": "http://sonarr:8989", "ApiKey": keys["sonarr"]}],
        "QueueRules": INFINIDYSK_QUEUE_RULES,
    }
    serialized = json.dumps(desired, separators=(",", ":"))
    current_raw = media_env.get("INFINIDYSK_ARR_INSTANCES")
    try:
        current = json.loads(current_raw) if current_raw else None
    except json.JSONDecodeError as exc:
        raise WireError(
            "INFINIDYSK_ARR_INSTANCES in stacks/media-server/.env is invalid JSON"
        ) from exc
    if current == desired:
        return None

    def apply() -> None:
        media_env.set("INFINIDYSK_ARR_INSTANCES", serialized)
        media_env.write()
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(MEDIA_COMPOSE),
                "up",
                "-d",
                "infinidysk",
            ],
            "recreate InfiniDysk with Arr connections",
        )

    return Change(
        "infinidysk",
        "register Sonarr and Radarr for health and queue management",
        [
            "Sonarr: http://sonarr:8989",
            "Radarr: http://radarr:7878",
            "API keys: redacted",
            f"queue rules: {len(INFINIDYSK_QUEUE_RULES)}",
        ],
        apply,
    )


def sonarr_unknown_quality_change(http: DockerHTTP, key: str) -> Change | None:
    """Keep Sonarr's "Unknown" quality sizes within this stack's size cap.

    TRaSH quality-size resources cover every real quality but omit "Unknown",
    and recyclarr only manages qualities present in the guide (overriding one
    that is absent is a hard config error), so Unknown keeps Sonarr's shipped
    default max of 199.9 MB/min. Sonarr checks a season pack against the combined
    runtime of its episodes. Set Unknown's preferred and maximum sizes to the
    same 375 MB/min cap configured for the managed qualities; daily Recyclarr
    sync leaves this unmanaged quality alone.
    """
    desired = {"minSize": 5.0, "preferredSize": 375.0, "maxSize": 375.0}
    endpoint = "http://sonarr:8989/api/v3/qualitydefinition"
    current = http.request("sonarr", "GET", endpoint, key)
    items = current if isinstance(current, list) else []
    unknown = next(
        (
            item
            for item in items
            if (item.get("quality") or {}).get("name") == "Unknown"
        ),
        None,
    )
    if not unknown:
        return None

    payload = json.loads(json.dumps(unknown))
    changed = []
    for name, value in desired.items():
        old = unknown.get(name)
        if old is None or abs(float(old) - value) > 1e-9:
            changed.append(f"{name}: {old} -> {value}")
            payload[name] = value
    if not changed:
        return None
    return Change(
        "sonarr",
        "set Unknown quality sizes to the guide convention",
        changed,
        lambda: http.request(
            "sonarr", "PUT", f"{endpoint}/{unknown['id']}", key, payload
        ),
    )


def prowlarr_change(
    http: DockerHTTP, token: str, keys: dict[str, str]
) -> Change | None:
    endpoint = "http://prowlarr:9696/api/v1/applications"
    current = http.request("prowlarr", "GET", endpoint, token)
    desired = {
        "Sonarr": ("http://sonarr:8989", keys["sonarr"]),
        "Radarr": ("http://radarr:7878", keys["radarr"]),
    }
    changes: list[str] = []
    updates: list[tuple[str, dict[str, Any]]] = []
    for name, (base_url, key) in desired.items():
        existing = next(
            (app for app in current if app.get("name", "").lower() == name.lower()),
            None,
        )
        if existing:
            payload = json.loads(json.dumps(existing))
            local_changes = []
            if existing.get("syncLevel") != "fullSync":
                local_changes.append(
                    f"syncLevel: {existing.get('syncLevel')} -> fullSync"
                )
                payload["syncLevel"] = "fullSync"
            app_fields = [
                ("baseUrl", base_url),
                ("prowlarrUrl", "http://prowlarr:9696"),
            ]
            for field, value in app_fields:
                old = field_value(existing, field)
                if old != value:
                    local_changes.append(
                        f"{field}: {redacted(old, field)} -> {redacted(value, field)}"
                    )
                    set_field(payload, field, value)
            # Prowlarr masks the linked app's apiKey on read-back, so a literal
            # comparison never converges. Verify the stored key by testing the
            # application link; only a failing test rewrites the key.
            try:
                http.request(
                    "prowlarr",
                    "POST",
                    f"{endpoint}/test?forceTest=true",
                    token,
                    json.loads(json.dumps(existing)),
                )
            except WireError:
                set_field(payload, "apiKey", key)
                local_changes.append(
                    f"apiKey: {redacted(field_value(existing, 'apiKey'), 'apiKey')} "
                    f"-> {redacted(key, 'apiKey')}"
                )
            if local_changes:
                changes.extend([f"{name} {item}" for item in local_changes])
                updates.append(
                    (
                        f"http://prowlarr:9696/api/v1/applications/{existing['id']}",
                        payload,
                    )
                )
            continue
        payload = {
            "name": name,
            "implementation": name,
            "implementationName": name,
            "configContract": f"{name}Settings",
            "enable": True,
            "syncLevel": "fullSync",
            "fields": [
                {"name": "prowlarrUrl", "value": "http://prowlarr:9696"},
                {"name": "baseUrl", "value": base_url},
                {"name": "apiKey", "value": key},
            ],
            "tags": [],
        }
        changes.append(f"add {name}: {base_url}")
        updates.append((endpoint, payload))
    if not changes:
        return None

    def apply() -> None:
        for url, payload in updates:
            http.request(
                "prowlarr", "PUT" if payload.get("id") else "POST", url, token, payload
            )

    return Change("prowlarr", "update Arr applications", changes, apply)


def bazarr_change(
    config_dir: Path, http: DockerHTTP, keys: dict[str, str]
) -> Change | None:
    config_path, bazarr_key = bazarr_api_key(config_dir)
    endpoint = "http://bazarr:6767/api/system/settings"
    current = http.request("bazarr", "GET", endpoint, bazarr_key)
    general = current.get("general", {})
    desired = {
        "settings-general-use_sonarr": (general.get("use_sonarr"), True),
        "settings-sonarr-ip": (current.get("sonarr", {}).get("ip"), "sonarr"),
        "settings-sonarr-port": (current.get("sonarr", {}).get("port"), 8989),
        # Bazarr serializes the root URL base as "", so match its own
        # representation rather than fighting it with "/".
        "settings-sonarr-base_url": (
            current.get("sonarr", {}).get("base_url") or "",
            "",
        ),
        "settings-sonarr-ssl": (current.get("sonarr", {}).get("ssl"), False),
        "settings-general-use_radarr": (general.get("use_radarr"), True),
        "settings-radarr-ip": (current.get("radarr", {}).get("ip"), "radarr"),
        "settings-radarr-port": (current.get("radarr", {}).get("port"), 7878),
        "settings-radarr-base_url": (
            current.get("radarr", {}).get("base_url") or "",
            "",
        ),
        "settings-radarr-ssl": (current.get("radarr", {}).get("ssl"), False),
    }
    # Bazarr intentionally masks connected-app API keys in its API response.
    # Read only those two scalar values from its own config to make reruns
    # idempotent; no Bazarr settings are edited directly.
    stored_keys = {
        "settings-sonarr-apikey": yaml_section_value(config_path, "sonarr", "apikey"),
        "settings-radarr-apikey": yaml_section_value(config_path, "radarr", "apikey"),
    }
    desired.update(
        {
            "settings-sonarr-apikey": (
                stored_keys["settings-sonarr-apikey"],
                keys["sonarr"],
            ),
            "settings-radarr-apikey": (
                stored_keys["settings-radarr-apikey"],
                keys["radarr"],
            ),
        }
    )

    form: dict[str, Any] = {}
    changes = []
    for field, (old, value) in desired.items():
        normalized_old = str(old).lower() if isinstance(old, bool) else str(old)
        normalized_value = str(value).lower() if isinstance(value, bool) else str(value)
        if normalized_old == normalized_value:
            continue
        form[field] = normalized_value
        if "apikey" in field:
            display = "secret redacted"
        else:
            display = f"{old} -> {value}"
        changes.append(f"{field}: {display}")
    if not changes:
        return None

    return Change(
        "bazarr",
        "update Sonarr/Radarr connections",
        changes,
        lambda: http.request("bazarr", "POST", endpoint, bazarr_key, form=form),
    )


def jellyfin_library_selections(http: DockerHTTP, token: str) -> dict[str, list[str]]:
    """Return Bazarr's names and ids for Jellyfin movie and TV libraries."""
    libraries = http.request(
        "jellyfin",
        "GET",
        "http://jellyfin:8096/Library/VirtualFolders",
        headers={"Authorization": f'MediaBrowser Token="{token}"'},
    )
    if not isinstance(libraries, list):
        raise WireError("Jellyfin returned an invalid library list")

    selected: dict[str, list[tuple[str, str]]] = {"movie": [], "series": []}
    for library in libraries:
        collection = library.get("CollectionType")
        kind = (
            "movie"
            if collection == "movies"
            else "series"
            if collection == "tvshows"
            else None
        )
        library_id = library.get("ItemId")
        name = library.get("Name")
        if kind and library_id and name:
            selected[kind].append((str(name), str(library_id)))

    return {
        "movie_library": [name for name, _ in sorted(selected["movie"])],
        "movie_library_ids": [
            library_id for _, library_id in sorted(selected["movie"])
        ],
        "series_library": [name for name, _ in sorted(selected["series"])],
        "series_library_ids": [
            library_id for _, library_id in sorted(selected["series"])
        ],
    }


def bazarr_jellyfin_change(
    config_dir: Path,
    http: DockerHTTP,
    jellyfin_key: Callable[[], str | None],
    dry_run: bool = False,
) -> Change | None:
    """Enable Bazarr's Jellyfin refresh integration and select its libraries."""
    config_path, bazarr_key = bazarr_api_key(config_dir)
    endpoint = "http://bazarr:6767/api/system/settings"
    current = http.request("bazarr", "GET", endpoint, bazarr_key)
    general = current.get("general", {})
    jellyfin = current.get("jellyfin", {})

    # Read Bazarr's persisted scalar so key rotation converges even if its API
    # response omits or masks the connected service key.
    stored_key = yaml_section_value(config_path, "jellyfin", "apikey")
    token = stored_key if stored_key and jellyfin_key_valid(http, stored_key) else None
    if token is None:
        token = jellyfin_key()

    if token is None:
        if not dry_run:
            return None
        # There is no key to enumerate the libraries in a preview. Still report
        # the planned integration; the apply closure is not run during --dry-run.

        def apply_after_key_provisioning() -> None:
            resolved = jellyfin_key()
            if resolved is None:
                raise WireError("could not obtain a Jellyfin API key for Bazarr")
            discovered = jellyfin_library_selections(http, resolved)
            http.request(
                "bazarr",
                "POST",
                endpoint,
                bazarr_key,
                form={
                    "settings-general-use_jellyfin": True,
                    "settings-jellyfin-url": "http://jellyfin:8096",
                    "settings-jellyfin-apikey": resolved,
                    "settings-jellyfin-refresh_method": "immediate",
                    "settings-jellyfin-update_movie_library": True,
                    "settings-jellyfin-update_series_library": True,
                    "settings-jellyfin-movie_library": discovered["movie_library"],
                    "settings-jellyfin-movie_library_ids": discovered[
                        "movie_library_ids"
                    ],
                    "settings-jellyfin-series_library": discovered["series_library"],
                    "settings-jellyfin-series_library_ids": discovered[
                        "series_library_ids"
                    ],
                },
            )

        return Change(
            "bazarr",
            "connect to Jellyfin for subtitle refreshes",
            [
                "enabled: True",
                "server: http://jellyfin:8096",
                "API key: provision/reuse a Jellyfin key (redacted)",
                "movie and show libraries: discover when a key is available",
                "refresh metadata after movie and episode subtitle changes",
            ],
            apply_after_key_provisioning,
        )

    libraries = jellyfin_library_selections(http, token)
    desired: dict[str, Any] = {
        "settings-general-use_jellyfin": True,
        "settings-jellyfin-url": "http://jellyfin:8096",
        "settings-jellyfin-apikey": token,
        "settings-jellyfin-refresh_method": "immediate",
        "settings-jellyfin-update_movie_library": True,
        "settings-jellyfin-update_series_library": True,
        "settings-jellyfin-movie_library": libraries["movie_library"],
        "settings-jellyfin-movie_library_ids": libraries["movie_library_ids"],
        "settings-jellyfin-series_library": libraries["series_library"],
        "settings-jellyfin-series_library_ids": libraries["series_library_ids"],
    }
    existing: dict[str, Any] = {
        "settings-general-use_jellyfin": general.get("use_jellyfin"),
        "settings-jellyfin-url": jellyfin.get("url"),
        "settings-jellyfin-apikey": stored_key,
        "settings-jellyfin-refresh_method": jellyfin.get("refresh_method"),
        "settings-jellyfin-update_movie_library": jellyfin.get("update_movie_library"),
        "settings-jellyfin-update_series_library": jellyfin.get(
            "update_series_library"
        ),
        "settings-jellyfin-movie_library": jellyfin.get("movie_library") or [],
        "settings-jellyfin-movie_library_ids": jellyfin.get("movie_library_ids") or [],
        "settings-jellyfin-series_library": jellyfin.get("series_library") or [],
        "settings-jellyfin-series_library_ids": jellyfin.get("series_library_ids")
        or [],
    }

    def normalized(value: Any, field: str) -> Any:
        if field in {
            "settings-jellyfin-movie_library",
            "settings-jellyfin-movie_library_ids",
            "settings-jellyfin-series_library",
            "settings-jellyfin-series_library_ids",
        }:
            return sorted(str(item) for item in (value or []))
        return value

    form: dict[str, Any] = {}
    changes = []
    for field, value in desired.items():
        old = existing[field]
        if normalized(old, field) == normalized(value, field):
            continue
        form[field] = value
        if "apikey" in field:
            display = "secret redacted"
        elif isinstance(value, list):
            display = f"{len(old or [])} -> {len(value)} selected"
        else:
            display = f"{old} -> {value}"
        changes.append(f"{field}: {display}")
    if not changes:
        return None

    return Change(
        "bazarr",
        "update Jellyfin connection and subtitle refresh settings",
        changes,
        lambda: http.request("bazarr", "POST", endpoint, bazarr_key, form=form),
    )


def recyclarr_change(config_dir: Path, keys: dict[str, str]) -> Change | None:
    path = config_dir / "recyclarr" / "secrets.yml"
    desired = (
        "# rendered by just wire - do not edit\n"
        f"radarr_api_key: {keys['radarr']}\n"
        f"sonarr_api_key: {keys['sonarr']}\n"
    )
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    secure = path.exists() and (path.stat().st_mode & 0o777) == 0o600
    if current == desired and secure:
        return None

    changed = []
    for app in ("radarr", "sonarr"):
        changed.append(f"{app}_api_key: update (secret redacted)")

    def apply() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".secrets.", dir=path.parent, text=True
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(desired)
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise WireError(f"could not write {path}: {exc}") from exc

        compose = ROOT / "stacks" / "media-server" / "compose.yaml"
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(compose),
                "up",
                "-d",
                "--force-recreate",
                "recyclarr",
            ],
            "recreate recyclarr",
        )
        for attempt in range(1, 4):
            try:
                run_command(
                    [
                        "docker",
                        "compose",
                        "-f",
                        str(compose),
                        "exec",
                        "-T",
                        "recyclarr",
                        "recyclarr",
                        "sync",
                    ],
                    "initial recyclarr sync",
                )
                return
            except WireError:
                if attempt == 3:
                    raise
                time.sleep(10)

    return Change(
        "recyclarr", "update API secrets and run initial sync", changed, apply
    )


def jellyfin_key_valid(http: DockerHTTP, key: str) -> bool:
    try:
        http.request(
            "jellyfin",
            "GET",
            "http://jellyfin:8096/System/Info",
            headers={"Authorization": f'MediaBrowser Token="{key}"'},
        )
    except WireError:
        return False
    return True


def jellyfin_prompt_credentials(default_username: str | None = None) -> tuple[str, str]:
    username = (
        input(
            "Jellyfin admin username"
            + (f" [{default_username}]" if default_username else "")
            + ": "
        ).strip()
        or default_username
        or ""
    )
    if not username:
        raise WireError("no Jellyfin admin username provided")
    password = getpass.getpass("Jellyfin admin password: ")
    if not password:
        raise WireError("Jellyfin admin password must not be empty")
    return username, password


jellyfin_credentials: dict[str, str] = {}


def obtain_jellyfin_credentials(
    default_username: str | None = None,
) -> tuple[str, str]:
    """Return the Jellyfin admin credentials, prompting only once per run.

    Seerr bootstraps its admin account through the same Jellyfin login, so a run
    that already prompted for Jellyfin reuses those credentials in memory instead
    of prompting twice. Nothing is written to disk.
    """
    if "username" in jellyfin_credentials:
        return jellyfin_credentials["username"], jellyfin_credentials["password"]
    username, password = jellyfin_prompt_credentials(default_username)
    jellyfin_credentials.update(username=username, password=password)
    return username, password


def jellyfin_authenticate(
    http: DockerHTTP, base: str, username: str, password: str
) -> str:
    device = (
        'MediaBrowser Client="kickstarrt", Device="just wire", '
        'DeviceId="kickstarrt-wire", Version="1.0"'
    )
    auth = http.request(
        "jellyfin",
        "POST",
        f"{base}/Users/AuthenticateByName",
        body={"Username": username, "Pw": password},
        # Jellyfin 12 disables the legacy X-Emby-Authorization header by default.
        headers={"Authorization": device},
    )
    token = auth.get("AccessToken") if isinstance(auth, dict) else None
    if not token:
        raise WireError(
            "Jellyfin did not accept the admin credentials (no access token returned)"
        )
    return token


def jellyfin_mint_key(http: DockerHTTP, base: str, token: str) -> str:
    authorized = {"Authorization": f'MediaBrowser Token="{token}"'}
    listed = http.request("jellyfin", "GET", f"{base}/Auth/Keys", headers=authorized)
    items = listed.get("Items", []) if isinstance(listed, dict) else []
    candidates = [item for item in items if item.get("AppName") == "Kickstarrt"]
    if candidates:
        newest = max(candidates, key=lambda item: str(item.get("DateCreated") or ""))
        existing = newest.get("AccessToken")
        if existing:
            return existing
    http.request(
        "jellyfin", "POST", f"{base}/Auth/Keys?app=Kickstarrt", headers=authorized
    )
    listed = http.request("jellyfin", "GET", f"{base}/Auth/Keys", headers=authorized)
    items = listed.get("Items", []) if isinstance(listed, dict) else []
    candidates = [item for item in items if item.get("AppName") == "Kickstarrt"]
    if not candidates:
        raise WireError(
            "Jellyfin created the Kickstarrt API key but GET /Auth/Keys did not list it"
        )
    newest = max(candidates, key=lambda item: str(item.get("DateCreated") or ""))
    key = newest.get("AccessToken")
    if not key:
        raise WireError("Jellyfin listed the Kickstarrt API key without an AccessToken")
    return key


def jellyfin_mint_first_run(http: DockerHTTP, dry_run: bool, yes: bool) -> str | None:
    """Create a Jellyfin API key, bootstrapping it when possible.

    On a fresh install the wizard API creates the admin account first. If the
    wizard is already complete (credentials exist) the key is minted through an
    existing admin login instead, prompted interactively; `--yes` cannot prompt,
    so that path is skipped with an error.
    """
    base = "http://jellyfin:8096"
    try:
        http.request("jellyfin", "GET", f"{base}/Startup/Configuration")
        first_run = True
    except HTTPWireError as exc:
        if exc.status in (401, 403):
            first_run = False
        else:
            raise
    if dry_run:
        if first_run:
            print(
                "Jellyfin: first run detected - `just wire` would create the admin "
                "account and a Kickstarrt API key, then configure the Sonarr/Radarr -> "
                "Jellyfin scan connections",
            )
        else:
            print(
                "Jellyfin: no Kickstarrt API key in use - `just wire` would authenticate "
                "as the Jellyfin admin and mint a Kickstarrt API key, then configure the "
                "Sonarr/Radarr -> Jellyfin scan connections",
            )
        return None
    if not first_run and yes:
        print(
            "error: no Jellyfin API key is in use and the setup wizard is already "
            "complete; --yes cannot prompt for admin credentials. Run `just wire` "
            "in a terminal to mint a key, or create one in Jellyfin -> Dashboard -> "
            "API Keys and re-run (Jellyfin wiring skipped)",
            file=sys.stderr,
        )
        return None
    if not sys.stdin.isatty():
        print(
            "warning: Jellyfin has no usable API key; run `just wire` in a terminal "
            "to create one (Jellyfin wiring skipped)",
            file=sys.stderr,
        )
        return None
    if first_run:
        print(
            "Jellyfin is in first-run state; creating the admin account and an API key."
        )
    else:
        print(
            "Jellyfin has no usable API key; authenticating as the admin to mint one."
        )
    username, password = obtain_jellyfin_credentials(
        default_username="jellyfin" if first_run else None
    )
    try:
        if first_run:
            http.request(
                "jellyfin",
                "POST",
                f"{base}/Startup/User",
                body={"Name": username, "Password": password},
            )
            http.request("jellyfin", "POST", f"{base}/Startup/Complete")
        token = jellyfin_authenticate(http, base, username, password)
    except HTTPWireError as exc:
        if first_run and exc.status in (400, 403, 404):
            print(
                f"warning: Jellyfin first-run bootstrap refused (HTTP {exc.status}); "
                "the wizard is probably already configured - generate a key in "
                "Jellyfin -> Dashboard -> API Keys (Jellyfin wiring skipped)",
                file=sys.stderr,
            )
            return None
        raise
    return jellyfin_mint_key(http, base, token)


def get_jellyfin_key(
    http: DockerHTTP, keys: dict[str, str], dry_run: bool = False, yes: bool = False
) -> str | None:
    """Return a live Jellyfin API key or None.

    A key already stored in the *arr Jellyfin connections is reused once it is
    validated against Jellyfin, so a revoked or rotated key is detected. With no
    usable key, a new one is minted when possible: through the first-run wizard
    bootstrap on a fresh install, or interactively through an existing admin
    login once the wizard is complete.
    """
    for app in ("sonarr", "radarr"):
        port = 8989 if app == "sonarr" else 7878
        current = http.request(
            app, "GET", f"http://{app}:{port}/api/v3/notification", keys[app]
        )
        existing = next(
            (
                connection
                for connection in current
                if connection.get("implementation") == "MediaBrowser"
            ),
            None,
        )
        candidate = field_value(existing, "apiKey") if existing else None
        if candidate and jellyfin_key_valid(http, candidate):
            return candidate
    return jellyfin_mint_first_run(http, dry_run, yes)


def arr_jellyfin_notification(
    http: DockerHTTP,
    app: str,
    key: str,
    jellyfin_key: Callable[[], str | None],
) -> Change | None:
    """Reconcile the *arr -> Jellyfin connection that scans the library on imports.

    The *arr APIs mask the connection's stored apiKey on read-back, so a literal
    comparison never converges. Instead the stored key is verified by running the
    notification's own test endpoint: a connection that still tests OK is left
    alone (masked value preserved on any unrelated update), and only a failing
    test triggers a key rewrite with a freshly validated Jellyfin key. That key is
    resolved lazily through ``jellyfin_key``, so converged runs never prompt.
    """
    port = 8989 if app == "sonarr" else 7878
    endpoint = f"http://{app}:{port}/api/v3/notification"
    current = http.request(app, "GET", endpoint, key)
    existing = next(
        (
            connection
            for connection in current
            if connection.get("implementation") == "MediaBrowser"
        ),
        None,
    )
    desired_fields = {
        "host": "jellyfin",
        "port": 8096,
        "useSsl": False,
        "notify": False,
        "updateLibrary": True,
    }
    triggers = {
        "onGrab": False,
        "onDownload": True,
        "onUpgrade": True,
        "onRename": True,
    }
    if existing:
        payload = json.loads(json.dumps(existing))
        changed = []
        for name, value in desired_fields.items():
            old = field_value(existing, name)
            if old != value:
                changed.append(
                    f"{name}: {redacted(old, name)} -> {redacted(value, name)}"
                )
                set_field(payload, name, value)
        for name, value in triggers.items():
            old = existing.get(name)
            if old != value:
                changed.append(f"{name}: {old} -> {value}")
                payload[name] = value
        if existing.get("name") != "Jellyfin":
            changed.append(f"name: {existing.get('name')} -> Jellyfin")
            payload["name"] = "Jellyfin"
        try:
            http.request(
                app,
                "POST",
                f"{endpoint}/test?forceTest=true",
                key,
                json.loads(json.dumps(existing)),
            )
        except WireError:
            token = jellyfin_key()
            if token is None:
                return None
            set_field(payload, "apiKey", token)
            changed.append("apiKey: <unchanged secret> -> <unchanged secret>")
        if not changed:
            return None
        return Change(
            app,
            "update Jellyfin scan connection",
            changed,
            lambda: http.request(
                app, "PUT", f"{endpoint}/{existing['id']}", key, payload
            ),
        )

    token = jellyfin_key()
    if token is None:
        return None
    payload = {
        "name": "Jellyfin",
        "implementation": "MediaBrowser",
        "implementationName": "Emby / Jellyfin",
        "configContract": "MediaBrowserSettings",
        "fields": [
            {"name": name, "value": value} for name, value in desired_fields.items()
        ]
        + [{"name": "apiKey", "value": token}],
        **triggers,
    }
    return Change(
        app,
        "create Jellyfin scan connection",
        [
            f"{field}: {redacted(value, field)}"
            for field, value in desired_fields.items()
        ]
        + ["apiKey: <unchanged secret>"],
        lambda: http.request(app, "POST", endpoint, key, payload),
    )


def seerr_mint_first_run(http: DockerHTTP, key: str, dry_run: bool, yes: bool) -> bool:
    """Bring Seerr to a fully-wired state, bootstrapping first-run when possible.

    Returns True once Seerr has an admin user, is marked initialized, and holds a
    Jellyfin connection, so the caller can reconcile the Jellyfin and *arr
    connections. Seerr creates that admin through a Jellyfin admin login; the
    credentials captured earlier in the same ``just wire`` run are reused,
    otherwise one interactive prompt happens here. ``--yes`` cannot prompt, so an
    uninitialized (or Jellyfin-less) Seerr is skipped with an error.
    """
    base = SEERR_URL
    try:
        public = http.request("seerr", "GET", f"{base}/api/v1/settings/public")
    except WireError:
        print(
            "warning: Seerr API is unreachable; finish the Seerr setup wizard or "
            "bring the seerr service up, then re-run `just wire` (Seerr wiring "
            "skipped)",
            file=sys.stderr,
        )
        return False
    initialized = bool(isinstance(public, dict) and public.get("initialized"))
    if initialized:
        try:
            current = http.request(
                "seerr", "GET", f"{base}/api/v1/settings/jellyfin", key
            )
        except WireError as exc:
            print(
                "warning: Seerr rejected the API key read from "
                "data/seerr/config/settings.json; regenerate it in Seerr -> Settings "
                f"and re-run `just wire` ({exc}) (Seerr wiring skipped)",
                file=sys.stderr,
            )
            return False
        if isinstance(current, dict) and current.get("apiKey"):
            return True

    if dry_run:
        if not initialized:
            print(
                "Seerr: first run detected - `just wire` would create the admin "
                "account and configure the Jellyfin and Sonarr/Radarr connections",
            )
        else:
            print(
                "Seerr: initialized but has no Jellyfin connection - `just wire` "
                "would complete the Jellyfin login and configure the Sonarr/Radarr "
                "connections",
            )
        return False
    if yes or not sys.stdin.isatty():
        print(
            f"error: Seerr has not completed its "
            f"{'first-run setup' if not initialized else 'Jellyfin connection'} "
            "and --yes cannot prompt for the Jellyfin admin credentials it needs; "
            "finish the setup in the Seerr UI or run `just wire` in a terminal "
            "(Seerr wiring skipped)",
            file=sys.stderr,
        )
        return False
    if not initialized:
        print(
            "Seerr is in first-run state; creating the admin account via the "
            "Jellyfin login."
        )
    else:
        print(
            "Seerr has no Jellyfin connection; linking it through the Jellyfin login."
        )
    username, password = obtain_jellyfin_credentials()
    try:
        http.request(
            "seerr",
            "POST",
            f"{base}/api/v1/auth/jellyfin",
            body={
                "username": username,
                "password": password,
                "hostname": SEERR_JELLYFIN_HOST,
                "port": SEERR_JELLYFIN_PORT,
                "useSsl": False,
                "urlBase": "",
                "serverType": SEERR_JELLYFIN_SERVER_TYPE,
            },
        )
    except HTTPWireError as exc:
        if "already configured" in str(exc).lower():
            print("note: Seerr already has a Jellyfin connection; proceeding")
        else:
            print(
                f"warning: Seerr first-run bootstrap failed: {exc}; finish the setup "
                "wizard in the Seerr UI and re-run (Seerr wiring skipped)",
                file=sys.stderr,
            )
            return False
    # The Jellyfin login just created (or refreshed) the admin user, so the
    # X-Api-Key path now passes the ADMIN check on the settings routes.
    try:
        http.request("seerr", "POST", f"{base}/api/v1/settings/initialize", key)
    except WireError as exc:
        print(
            f"warning: could not mark Seerr as initialized: {exc}",
            file=sys.stderr,
        )
    print("Applied: seerr - completed first-run setup.")
    return True


def seerr_jellyfin_change(http: DockerHTTP, key: str) -> Change | None:
    """Reconcile Seerr's Jellyfin connection and libraries.

    The connection's API key, server id and server name belong to Seerr's own
    Jellyfin login and are never overwritten here. Seerr cannot fill requests
    without at least one Jellyfin library, so the library list is re-synced and
    every movie/show library is enabled when discovery finds drift.
    """
    base = SEERR_URL
    current = http.request("seerr", "GET", f"{base}/api/v1/settings/jellyfin", key)
    payload = json.loads(json.dumps(current)) if isinstance(current, dict) else {}
    desired = {
        "ip": SEERR_JELLYFIN_HOST,
        "port": SEERR_JELLYFIN_PORT,
        "useSsl": False,
        "urlBase": "",
    }
    changed = []
    for name, value in desired.items():
        old = payload.get(name)
        if old != value:
            changed.append(f"{name}: {old} -> {value}")
            payload[name] = value
    try:
        settings_main = http.request(
            "seerr", "GET", f"{base}/api/v1/settings/main", key
        )
    except WireError:
        settings_main = {}
    media_server_type = settings_main.get("mediaServerType")
    if media_server_type != SEERR_JELLYFIN_SERVER_TYPE:
        changed.append(
            f"mediaServerType: {media_server_type} -> {SEERR_JELLYFIN_SERVER_TYPE}"
        )
    # Seerr 3.4.1's GET /settings/jellyfin/library mutates state: without an
    # `enable` query parameter it saves every library as disabled. Read the
    # library flags from the Jellyfin settings resource, which is read-only.
    stored = payload.get("libraries")
    libraries = stored if isinstance(stored, list) else []
    disabled = [lib for lib in libraries if not lib.get("enabled")]
    if not changed and not disabled and libraries:
        return None

    details = list(changed)
    if not libraries:
        details.append("sync and enable all Jellyfin libraries (none synced yet)")
    elif disabled:
        details.append(
            "enable "
            + ", ".join(f"{lib.get('name') or lib.get('id')}" for lib in disabled)
        )

    def apply() -> None:
        if changed:
            # POST validates and stores the connection; the apiKey, server id and
            # server name already stored by Seerr's own Jellyfin login are kept.
            http.request(
                "seerr", "POST", f"{base}/api/v1/settings/jellyfin", key, payload
            )
        try:
            # This stack pins Seerr 3.4.1, whose library sync and enable actions
            # are GET query parameters. Do not GET the bare library endpoint:
            # that version treats it as a write that disables every library.
            synced = http.request(
                "seerr",
                "GET",
                f"{base}/api/v1/settings/jellyfin/library?sync=1",
                key,
            )
        except HTTPWireError as exc:
            if "NoLibraries" in str(exc) or "GroupedFolders" in str(exc):
                raise WireError(
                    "Seerr found no Jellyfin media libraries; create them in "
                    "Jellyfin (Dashboard -> Media Libraries) and re-run"
                ) from exc
            raise
        except WireError as exc:
            raise WireError(f"could not sync Seerr Jellyfin libraries: {exc}") from exc

        libraries = synced if isinstance(synced, list) else []
        ids = [str(library["id"]) for library in libraries if library.get("id")]
        if ids:
            http.request(
                "seerr",
                "GET",
                f"{base}/api/v1/settings/jellyfin/library?enable={','.join(ids)}",
                key,
            )

        # Read back persisted state: some Seerr versions have changed library
        # mutation semantics, and a successful HTTP response alone is not enough
        # to ensure the next `just wire` run converges. The settings endpoint is
        # safe for this read on both old and current Seerr versions.
        verified_settings = http.request(
            "seerr", "GET", f"{base}/api/v1/settings/jellyfin", key
        )
        verified = (
            verified_settings.get("libraries")
            if isinstance(verified_settings, dict)
            else []
        )
        still_disabled = [
            library
            for library in (verified if isinstance(verified, list) else [])
            if library.get("enabled") is not True
        ]
        if still_disabled:
            names = ", ".join(
                str(library.get("name") or library.get("id"))
                for library in still_disabled
            )
            raise WireError(
                "Seerr still reports Jellyfin libraries as disabled after the "
                f"enable request: {names}"
            )

    return Change("seerr", "update Jellyfin connection", details, apply)


def seerr_arr_quality_profile(
    http: DockerHTTP, app: str, key: str, preferred: str = "Direct Play"
) -> dict[str, Any]:
    port = 8989 if app == "sonarr" else 7878
    profiles = http.request(
        app, "GET", f"http://{app}:{port}/api/v3/qualityprofile", key
    )
    profiles = profiles if isinstance(profiles, list) else []
    for profile in profiles:
        if profile.get("name") == preferred:
            return profile
    if profiles:
        return profiles[0]
    raise WireError(f"{app} has no quality profiles; run a Recyclarr sync first")


def seerr_arr_language_profile(http: DockerHTTP, app: str, key: str) -> int | None:
    """Return the first available Sonarr language profile id, or None."""
    port = 8989 if app == "sonarr" else 7878
    languages = http.request(
        app, "GET", f"http://{app}:{port}/api/v3/languageprofile", key
    )
    languages = languages if isinstance(languages, list) else []
    if not languages:
        return None
    return languages[0].get("id")


def seerr_arr_change(
    http: DockerHTTP,
    seerr_key: str,
    app: str,
    keys: dict[str, str],
    media_env: EnvFile,
) -> Change | None:
    """Reconcile one *arr server in Seerr (radarr -> movies, sonarr -> shows).

    The server is matched by its internal hostname and port. When it already
    exists, only the connection fields are re-asserted; the quality profile and
    any anime/language choices are left to the user. A new server pins the
    "Direct Play" profile, resolved from the server at apply time after
    Recyclarr has already synced in this run.
    """
    base = SEERR_URL
    display = "Sonarr" if app == "sonarr" else "Radarr"
    port = 8989 if app == "sonarr" else 7878
    domain = media_env.get("DOMAIN").strip()
    if not domain:
        raise WireError("DOMAIN is unset in stacks/media-server/.env")
    subdomain = media_env.get(f"SUB_DOMAIN_{app.upper()}") or app
    endpoint = f"{base}/api/v1/settings/{app}"
    servers = http.request("seerr", "GET", endpoint, seerr_key)
    servers = servers if isinstance(servers, list) else []
    existing = next(
        (
            server
            for server in servers
            if server.get("hostname") == app and server.get("port") == port
        ),
        None,
    )
    desired = {
        "name": display,
        "hostname": app,
        "port": port,
        "apiKey": keys[app],
        "useSsl": False,
        "baseUrl": "",
        "externalUrl": f"https://{subdomain}.{domain}",
        "activeDirectory": (
            "/mnt/usenet/library/shows"
            if app == "sonarr"
            else "/mnt/usenet/library/movies"
        ),
        "is4k": False,
        "syncEnabled": True,
        "preventSearch": False,
    }
    if existing:
        payload = json.loads(json.dumps(existing))
        # Seerr identifies the record in the URL; its request schema rejects
        # the read-only id field in the body.
        payload.pop("id", None)
        changed = []
        for name, value in desired.items():
            old = payload.get(name)
            if old != value:
                changed.append(
                    f"{name}: {redacted(old, name)} -> {redacted(value, name)}"
                )
                payload[name] = value
        if not changed:
            return None
        return Change(
            "seerr",
            f"update Seerr {display} server",
            changed,
            lambda: http.request(
                "seerr", "PUT", f"{endpoint}/{existing['id']}", seerr_key, payload
            ),
        )

    payload = dict(desired)
    payload["tags"] = []
    payload["isDefault"] = True
    if app == "sonarr":
        payload.update(
            {
                "seriesType": "standard",
                "enableSeasonFolders": True,
                "monitorNewItems": "all",
            }
        )
    else:
        payload["minimumAvailability"] = "announced"
    details = [f"{name}: {redacted(value, name)}" for name, value in desired.items()]
    details.append("activeProfileId: Direct Play (resolved from the server at apply)")
    if app == "sonarr":
        details.append("activeLanguageProfileId: first available (resolved at apply)")
    details.append("isDefault: True")

    def apply() -> None:
        body = json.loads(json.dumps(payload))
        profile = seerr_arr_quality_profile(http, app, keys[app])
        body["activeProfileId"] = profile["id"]
        body["activeProfileName"] = profile["name"]
        if app == "sonarr":
            try:
                language_id = seerr_arr_language_profile(http, app, keys[app])
            except WireError:
                language_id = None
            if language_id:
                body["activeLanguageProfileId"] = language_id
        http.request("seerr", "POST", endpoint, seerr_key, body)

    return Change("seerr", f"create Seerr {display} server", details, apply)


def maintainerr_result(
    response: Any,
    operation: str,
    *,
    require_ok: bool = False,
    secrets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Check Maintainerr's in-band response status and redact any echoed secrets."""
    if not isinstance(response, dict):
        raise WireError(f"Maintainerr {operation} returned an unexpected response")
    status = response.get("status")
    code = response.get("code")
    if status == "NOK" or code == 0 or (require_ok and status != "OK"):
        detail = str(response.get("message") or "request failed")
        for secret in secrets:
            if secret:
                detail = detail.replace(secret, "<redacted>")
        raise WireError(f"Maintainerr {operation} failed: {detail}")
    return response


def maintainerr_read(http: DockerHTTP, endpoint: str, operation: str) -> dict[str, Any]:
    response = http.request("maintainerr", "GET", f"{MAINTAINERR_URL}{endpoint}")
    return maintainerr_result(response, operation)


def maintainerr_jellyfin_change(
    http: DockerHTTP,
    jellyfin_key: Callable[[], str | None],
    *,
    dry_run: bool,
) -> Change | None:
    """Configure Maintainerr's Jellyfin connection without switching other servers."""
    current = maintainerr_read(http, "/api/settings/jellyfin", "read Jellyfin settings")
    setup_complete = http.request(
        "maintainerr", "GET", f"{MAINTAINERR_URL}/api/settings/test/setup"
    )
    if not isinstance(setup_complete, bool):
        raise WireError("Maintainerr returned an invalid media-server setup status")
    active_type = ""
    if setup_complete:
        server_type = http.request(
            "maintainerr", "GET", f"{MAINTAINERR_URL}/api/media-server/type"
        )
        active_type = (
            str(server_type.get("type") or "").strip().lower()
            if isinstance(server_type, dict)
            else ""
        )
        if not active_type:
            raise WireError(
                "Maintainerr could not identify its configured media server"
            )
    if active_type and active_type != "jellyfin":
        print(
            "warning: Maintainerr is configured for a different media server; "
            "skipping its Jellyfin connection (switch it in Maintainerr first)",
            file=sys.stderr,
        )
        return None

    desired_url = "http://jellyfin:8096"
    stored_key = current.get("jellyfin_api_key")
    stored_key = stored_key if isinstance(stored_key, str) else ""
    valid_stored_key = bool(stored_key) and jellyfin_key_valid(http, stored_key)
    token = stored_key if valid_stored_key else jellyfin_key()
    if token is None and not dry_run:
        print(
            "warning: no Jellyfin API key is available; skipping Maintainerr's "
            "Jellyfin connection (run `just wire` in a terminal after Jellyfin setup)",
            file=sys.stderr,
        )
        return None

    old_url = current.get("jellyfin_url") or ""
    desired_user_id = current.get("jellyfin_user_id") or ""
    if old_url != desired_url:
        desired_user_id = ""
    changed = []
    if active_type != "jellyfin":
        changed.append(f"media server: {active_type or '<unset>'} -> jellyfin")
    if old_url != desired_url:
        changed.append(f"jellyfin_url: set to {desired_url}")
    if not valid_stored_key:
        changed.append("jellyfin_api_key: update (secret redacted)")
    if (current.get("jellyfin_user_id") or "") != desired_user_id:
        changed.append("jellyfin_user_id: update (admin user auto-detected)")
    if not changed:
        return None

    def apply() -> None:
        api_key = token or jellyfin_key()
        if not api_key:
            raise WireError("could not obtain a Jellyfin API key for Maintainerr")
        payload = {
            "jellyfin_url": desired_url,
            "jellyfin_api_key": api_key,
            "jellyfin_user_id": desired_user_id,
        }
        result = http.request(
            "maintainerr",
            "POST",
            f"{MAINTAINERR_URL}/api/settings/jellyfin",
            body=payload,
        )
        maintainerr_result(
            result,
            "save Jellyfin connection",
            require_ok=True,
            secrets=(api_key,),
        )

    return Change(
        "maintainerr",
        "configure Jellyfin connection",
        changed,
        apply,
    )


def maintainerr_seerr_change(http: DockerHTTP, api_key: str) -> Change | None:
    """Configure Maintainerr's Seerr connection and verify it before saving."""
    current = maintainerr_read(http, "/api/settings/seerr", "read Seerr settings")
    url = f"{SEERR_URL}"
    if current.get("url") == url and current.get("api_key") == api_key:
        return None
    details = [
        f"url: set to {url}",
        f"api_key: {redacted(current.get('api_key'), 'api_key')} -> <unchanged secret>",
    ]

    def apply() -> None:
        payload = {"url": url, "api_key": api_key}
        tested = http.request(
            "maintainerr",
            "POST",
            f"{MAINTAINERR_URL}/api/settings/test/seerr",
            body=payload,
        )
        maintainerr_result(
            tested,
            "test Seerr connection",
            require_ok=True,
            secrets=(api_key,),
        )
        saved = http.request(
            "maintainerr",
            "POST",
            f"{MAINTAINERR_URL}/api/settings/seerr",
            body=payload,
        )
        maintainerr_result(
            saved,
            "save Seerr connection",
            require_ok=True,
            secrets=(api_key,),
        )

    return Change("maintainerr", "configure Seerr connection", details, apply)


def maintainerr_arr_change(http: DockerHTTP, app: str, api_key: str) -> Change | None:
    """Reconcile a Maintainerr Radarr or Sonarr instance, preserving other entries."""
    display = app.capitalize()
    port = 8989 if app == "sonarr" else 7878
    endpoint = f"/api/settings/{app}"
    current = http.request("maintainerr", "GET", f"{MAINTAINERR_URL}{endpoint}")
    if not isinstance(current, list):
        maintainerr_result(current, f"read {display} settings")
        raise WireError(f"Maintainerr returned an invalid {display} settings list")

    url = f"http://{app}:{port}"
    managed_name = f"Kickstarrt {display}"
    existing = next(
        (item for item in current if item.get("serverName") == managed_name), None
    )
    if existing is None:
        matching_url = [
            item
            for item in current
            if str(item.get("url") or "").rstrip("/").lower() == url
        ]
        if len(matching_url) > 1:
            raise WireError(
                f"Maintainerr has multiple {display} entries for {url}; "
                "remove the duplicate entries and re-run `just wire`"
            )
        existing = matching_url[0] if matching_url else None

    server_name = (
        existing.get("serverName")
        if existing and str(existing.get("url") or "").rstrip("/").lower() == url
        else managed_name
    )
    desired = {"serverName": server_name, "url": url, "apiKey": api_key}
    changed = []
    if existing:
        for field, value in desired.items():
            old = existing.get(field)
            if old != value:
                if field == "url":
                    changed.append(f"url: set to {url}")
                else:
                    changed.append(
                        f"{field}: {redacted(old, field)} -> {redacted(value, field)}"
                    )
        if not changed:
            return None
        instance_id = existing.get("id")
        if not isinstance(instance_id, int) or isinstance(instance_id, bool):
            raise WireError(
                f"Maintainerr's {display} entry has no valid id; "
                "repair it in Maintainerr and re-run `just wire`"
            )
        method = "PUT"
        save_url = f"{MAINTAINERR_URL}{endpoint}/{instance_id}"
        description = f"update {display} connection"
    else:
        desired["serverName"] = managed_name
        changed = [
            f"{field}: {redacted(value, field)}" for field, value in desired.items()
        ]
        method = "POST"
        save_url = f"{MAINTAINERR_URL}{endpoint}"
        description = f"create {display} connection"

    def apply() -> None:
        tested = http.request(
            "maintainerr",
            "POST",
            f"{MAINTAINERR_URL}/api/settings/test/{app}",
            body=desired,
        )
        maintainerr_result(
            tested,
            f"test {display} connection",
            require_ok=True,
            secrets=(api_key,),
        )
        saved = http.request("maintainerr", method, save_url, body=desired)
        maintainerr_result(
            saved,
            f"save {display} connection",
            secrets=(api_key,),
        )

    return Change("maintainerr", description, changed, apply)


def maintainerr_changes(
    http: DockerHTTP,
    keys: dict[str, str],
    seerr_key: str,
    jellyfin_key: Callable[[], str | None],
    *,
    dry_run: bool,
) -> list[Change]:
    """Build safe, idempotent connection changes; cleanup rules remain user-owned."""
    try:
        http.request("maintainerr", "GET", f"{MAINTAINERR_URL}/api/health/ready")
    except WireError as exc:
        print(
            "warning: Maintainerr is not ready; start its service and re-run "
            f"`just wire` (Maintainerr wiring skipped: {exc})",
            file=sys.stderr,
        )
        return []

    changes = []
    jellyfin = maintainerr_jellyfin_change(http, jellyfin_key, dry_run=dry_run)
    if jellyfin:
        changes.append(jellyfin)
    seerr = maintainerr_seerr_change(http, seerr_key)
    if seerr:
        changes.append(seerr)
    for app in ("radarr", "sonarr"):
        change = maintainerr_arr_change(http, app, keys[app])
        if change:
            changes.append(change)
    return changes


def confirm(change: Change) -> bool:
    print(f"\n{change.service}: {change.description}")
    for detail in change.details:
        print(f"  - {detail}")
    answer = input("Apply this change? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def run_wire(
    args: argparse.Namespace,
    http: DockerHTTP,
    config_dir: Path,
    keys: dict[str, str],
    media_env: EnvFile,
    infinidysk_api_key: str,
) -> int:
    try:
        changes: list[Change] = []
        infinidysk_change = infinidysk_arr_settings_change(media_env, keys)
        if infinidysk_change:
            changes.append(infinidysk_change)
        for app, path in (
            ("sonarr", "/mnt/usenet/library/shows"),
            ("radarr", "/mnt/usenet/library/movies"),
        ):
            change = root_folder_change(http, app, keys[app], path)
            if change:
                changes.append(change)
            change = arr_download_client(
                http,
                app,
                keys[app],
                "Sabnzbd",
                "SabnzbdSettings",
                "InfiniDysk (Usenet)",
                {
                    "host": "infinidysk",
                    "port": 3000,
                    "apiKey": infinidysk_api_key,
                },
            )
            if change:
                changes.append(change)
        jellyfin_key: str | None = None

        def resolve_jellyfin_key() -> str | None:
            nonlocal jellyfin_key
            if jellyfin_key is None:
                jellyfin_key = get_jellyfin_key(
                    http, keys, dry_run=args.dry_run, yes=args.yes
                )
            return jellyfin_key

        for app in ("sonarr", "radarr"):
            change = arr_jellyfin_notification(
                http, app, keys[app], resolve_jellyfin_key
            )
            if change:
                changes.append(change)
        unknown_quality = sonarr_unknown_quality_change(http, keys["sonarr"])
        if unknown_quality:
            changes.append(unknown_quality)
        for change in (
            prowlarr_change(http, keys["prowlarr"], keys),
            bazarr_change(config_dir, http, keys),
            bazarr_jellyfin_change(
                config_dir, http, resolve_jellyfin_key, dry_run=args.dry_run
            ),
            recyclarr_change(config_dir, keys),
        ):
            if change:
                changes.append(change)
        # Seerr changes are appended after Recyclarr so the Direct Play quality
        # profile it configures exists when a Seerr server is created.
        seerr_key = seerr_api_key(config_dir)
        if seerr_mint_first_run(http, seerr_key, args.dry_run, args.yes):
            for change in (
                seerr_jellyfin_change(http, seerr_key),
                seerr_arr_change(http, seerr_key, "radarr", keys, media_env),
                seerr_arr_change(http, seerr_key, "sonarr", keys, media_env),
            ):
                if change:
                    changes.append(change)
        changes.extend(
            maintainerr_changes(
                http,
                keys,
                seerr_key,
                resolve_jellyfin_key,
                dry_run=args.dry_run,
            )
        )
    except WireError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not changes:
        print("No wiring changes are needed.")
        return 0
    print(f"\nPlanned changes: {len(changes)} checkpoint(s)")
    if args.dry_run:
        for change in changes:
            print(f"\n{change.service}: {change.description}")
            for detail in change.details:
                print(f"  - {detail}")
        return 0

    applied = 0
    for change in changes:
        if not args.yes and not confirm(change):
            print("Skipped; stopping before the next checkpoint.")
            break
        try:
            change.apply()
        except WireError as exc:
            print(
                f"error applying {change.service}/{change.description}: {exc}",
                file=sys.stderr,
            )
            print(
                f"Applied {applied} checkpoint(s); stopping to avoid cascading changes.",
                file=sys.stderr,
            )
            return 1
        print(f"Applied: {change.service} - {change.description}")
        applied += 1
    print(f"Completed {applied}/{len(changes)} checkpoint(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactively wire the media services"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="discover and display changes without applying them",
    )
    parser.add_argument(
        "--yes", action="store_true", help="apply all planned changes without prompting"
    )
    args = parser.parse_args()
    if not args.dry_run and not args.yes and not sys.stdin.isatty():
        print(
            "refusing to mutate services without a terminal; use --yes explicitly",
            file=sys.stderr,
        )
        return 2

    config_dir = ROOT / "data"
    try:
        keys = {
            app: api_key(app, config_dir) for app in ("sonarr", "radarr", "prowlarr")
        }
        media_env = EnvFile(MEDIA_ENV)
        infinidysk_api_key = media_env.get("INFINIDYSK_API_KEY")
        if not infinidysk_api_key:
            raise WireError(
                "INFINIDYSK_API_KEY is unset; run `just init` before `just wire`"
            )
        with DockerHTTP() as http:
            return run_wire(args, http, config_dir, keys, media_env, infinidysk_api_key)
    except WireError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
