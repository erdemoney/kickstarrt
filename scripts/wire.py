#!/usr/bin/env python3
"""Interactively reconcile the stable, cross-service media wiring.

The script deliberately uses the applications' APIs instead of editing their
configuration files. HTTP is executed inside an existing container so Docker
service names (sonarr, radarr, etc.) remain private to the internal network.
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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
MEDIA_ENV = ROOT / "stacks" / "media-server" / ".env"

ZILEAN_URL = "http://zilean:8181"
ZILEAN_DEFINITION_FILE = "zilean"
ZILEAN_DEFINITION_URL = (
    "https://raw.githubusercontent.com/dreulavelle/Prowlarr-Indexers/"
    "9c0e9bdbed6fd13066c58397c713bac0a6173949/Custom/zilean.yml"
)

SEERR_URL = "http://seerr:5055"
SEERR_JELLYFIN_HOST = "jellyfin"
SEERR_JELLYFIN_PORT = 8096
SEERR_JELLYFIN_SERVER_TYPE = 2  # MediaServerType.JELLYFIN


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
    path = config_dir / app / "config.xml"
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError as exc:
        raise WireError(f"{path} does not exist; start {app} once first") from exc
    except ET.ParseError as exc:
        raise WireError(f"cannot parse {path}: {exc}") from exc
    key = root.findtext("ApiKey", "").strip()
    if not key:
        raise WireError(f"{path} does not contain an API key")
    return key


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
    """Run curl in a running container and return decoded JSON responses."""

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
        # Bazarr's and Seerr's images do not include curl. Sonarr is on the
        # same Docker network and is already used as the stack's internal HTTP
        # diagnostic container.
        transport = "sonarr" if source in ("bazarr", "seerr") else source
        command = [
            "docker",
            "exec",
            transport,
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
                command.extend(["--data-urlencode", f"{name}={value}"])
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
        except OSError as exc:
            raise WireError(f"could not run Docker: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip() or "curl failed"
            raise WireError(f"{source} request via {transport} failed: {detail}")
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
    desired_fields["tvCategory" if app == "sonarr" else "movieCategory"] = app
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
        secret_change = field_value(existing, "password") != desired_fields.get(
            "password"
        )
        if secret_change:
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
                # The Arr API masks or omits stored passwords. A successful
                # candidate test proves the existing secret works, so do not
                # prompt for or rewrite a secret-only difference.
                remove_field(payload, "password")
                changed = [item for item in changed if not item.startswith("password:")]
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
        "protocol": "torrent" if implementation == "QBittorrent" else "usenet",
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
            for field, value in (
                ("baseUrl", base_url),
                ("prowlarrUrl", "http://prowlarr:9696"),
            ):
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


def zilean_definition_path(config_dir: Path) -> Path:
    return (
        config_dir
        / "prowlarr"
        / "Definitions"
        / "Custom"
        / f"{ZILEAN_DEFINITION_FILE}.yml"
    )


def install_zilean_definition(config_dir: Path) -> None:
    """Fetch Zilean's Cardigann definition from a pinned upstream commit."""
    target = zilean_definition_path(config_dir)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".zilean.", dir=target.parent, text=True
    )
    os.close(descriptor)
    try:
        run_command(
            [
                "curl",
                "-fsSL",
                "--connect-timeout",
                "10",
                "--max-time",
                "60",
                ZILEAN_DEFINITION_URL,
                "-o",
                temporary,
            ],
            "download the Zilean indexer definition",
        )
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def prowlarr_zilean_change(
    http: DockerHTTP, token: str, config_dir: Path
) -> Change | None:
    """Reconcile the self-hosted Zilean indexer in Prowlarr.

    The stack ships Zilean (docs/indexers.md), so `just wire` keeps it
    registered: on a fresh box the Cardigann definition is downloaded from a
    pinned Prowlarr-Indexers commit, then the indexer is created or re-pointed
    at the internal service URL.
    """
    endpoint = "http://prowlarr:9696/api/v1/indexer"
    current = http.request("prowlarr", "GET", endpoint, token)
    existing = next(
        (
            indexer
            for indexer in current
            if indexer.get("implementation") == "Cardigann"
            and (
                field_value(indexer, "definitionFile") == ZILEAN_DEFINITION_FILE
                or indexer.get("name", "").lower() == "zilean"
            )
        ),
        None,
    )
    if existing:
        payload = json.loads(json.dumps(existing))
        changed = []
        for name, value in (
            ("definitionFile", ZILEAN_DEFINITION_FILE),
            ("baseUrl", ZILEAN_URL),
        ):
            old = field_value(existing, name)
            if old != value:
                changed.append(
                    f"{name}: {redacted(old, name)} -> {redacted(value, name)}"
                )
                set_field(payload, name, value)
        if existing.get("enable") is not True:
            changed.append(f"enable: {existing.get('enable')} -> True")
            payload["enable"] = True
        if not changed:
            return None
        return Change(
            "prowlarr",
            "re-point the self-hosted Zilean indexer",
            changed,
            lambda: http.request(
                "prowlarr",
                "PUT",
                f"{endpoint}/{existing['id']}",
                token,
                payload,
            ),
        )

    details = [
        f"definitionFile: {ZILEAN_DEFINITION_FILE}",
        f"baseUrl: {ZILEAN_URL}",
    ]
    if not zilean_definition_path(config_dir).exists():
        details.append(
            "would download zilean.yml from the pinned Prowlarr-Indexers commit"
        )

    def apply() -> None:
        install_zilean_definition(config_dir)
        run_command(
            [
                "docker",
                "compose",
                "-f",
                str(ROOT / "stacks" / "media-server" / "compose.yaml"),
                "up",
                "-d",
                "--force-recreate",
                "prowlarr",
            ],
            "recreate prowlarr",
        )
        payload = {
            "name": "Zilean",
            "implementation": "Cardigann",
            "implementationName": "Cardigann",
            "configContract": "CardigannSettings",
            "enable": True,
            "tags": [],
            "fields": [
                {"name": "definitionFile", "value": ZILEAN_DEFINITION_FILE},
                {"name": "baseUrl", "value": ZILEAN_URL},
            ],
        }
        for attempt in range(1, 4):
            try:
                profiles = http.request(
                    "prowlarr",
                    "GET",
                    "http://prowlarr:9696/api/v1/appprofile",
                    token,
                )
                if isinstance(profiles, list) and profiles:
                    ids = [p["id"] for p in profiles if p.get("id")]
                    if ids:
                        payload["appProfileId"] = min(ids)
                http.request("prowlarr", "POST", endpoint, token, payload)
                return
            except WireError:
                if attempt == 3:
                    raise
                time.sleep(10)

    return Change(
        "prowlarr",
        "create the self-hosted Zilean indexer",
        details,
        apply,
    )


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
        'DeviceId="kickstarrt-vps-wire", Version="1.0"'
    )
    auth = http.request(
        "jellyfin",
        "POST",
        f"{base}/Users/AuthenticateByName",
        body={"Username": username, "Pw": password},
        headers={"X-Emby-Authorization": device},
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
    stored = http.request(
        "seerr", "GET", f"{base}/api/v1/settings/jellyfin/library", key
    )
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
            synced = http.request(
                "seerr",
                "GET",
                f"{base}/api/v1/settings/jellyfin/library?sync=1",
                key,
            )
        except WireError as exc:
            if "NoLibraries" in str(exc) or "GroupedFolders" in str(exc):
                print(
                    "  note: Seerr found no Jellyfin media libraries; create them in "
                    "Jellyfin (Dashboard -> Media Libraries) and re-run",
                )
            else:
                print(f"  note: Seerr could not sync Jellyfin libraries: {exc}")
            return
        ids = []
        if isinstance(synced, list):
            ids = [lib["id"] for lib in synced if lib.get("id")]
        if ids:
            http.request(
                "seerr",
                "GET",
                f"{base}/api/v1/settings/jellyfin/library"
                f"?enable={','.join(str(library_id) for library_id in ids)}",
                key,
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
    http: DockerHTTP, seerr_key: str, app: str, keys: dict[str, str]
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
        "activeDirectory": "/mnt/shows" if app == "sonarr" else "/mnt/movies",
        "is4k": False,
        "syncEnabled": True,
        "preventSearch": False,
    }
    if existing:
        payload = json.loads(json.dumps(existing))
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


def confirm(change: Change) -> bool:
    print(f"\n{change.service}: {change.description}")
    for detail in change.details:
        print(f"  - {detail}")
    answer = input("Apply this change? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


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
        http = DockerHTTP()
        changes: list[Change] = []
        for app, path in (("sonarr", "/mnt/shows"), ("radarr", "/mnt/movies")):
            change = root_folder_change(http, app, keys[app], path)
            if change:
                changes.append(change)
            port = 8989 if app == "sonarr" else 7878
            for implementation, contract, name, fields in (
                (
                    "QBittorrent",
                    "QBittorrentSettings",
                    "Decypharr (debrid)",
                    {
                        "host": "decypharr",
                        "port": 8282,
                        "username": f"http://{app}:{port}",
                        "password": keys[app],
                    },
                ),
                (
                    "Sabnzbd",
                    "SabnzbdSettings",
                    "Decypharr (usenet)",
                    {
                        "host": "decypharr",
                        "port": 8282,
                        "urlBase": "/sabnzbd",
                        "username": f"http://{app}:{port}",
                        "password": keys[app],
                    },
                ),
            ):
                change = arr_download_client(
                    http, app, keys[app], implementation, contract, name, fields
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
        for change in (
            prowlarr_zilean_change(http, keys["prowlarr"], config_dir),
            prowlarr_change(http, keys["prowlarr"], keys),
            bazarr_change(config_dir, http, keys),
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
                seerr_arr_change(http, seerr_key, "radarr", keys),
                seerr_arr_change(http, seerr_key, "sonarr", keys),
            ):
                if change:
                    changes.append(change)
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


if __name__ == "__main__":
    raise SystemExit(main())
