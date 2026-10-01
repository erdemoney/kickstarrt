"""Small, dependency-free helpers shared by project administration scripts."""

from __future__ import annotations

import os
import ipaddress
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent.parent


class ScriptError(RuntimeError):
    """An expected, actionable administration-script failure."""


def read_arr_api_key(app: str, config_dir: Path) -> str:
    """Read an Arr API key from its persistent config.xml."""
    path = config_dir / app / "config.xml"
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError as exc:
        raise ScriptError(f"{path} does not exist; start {app} once first") from exc
    except ET.ParseError as exc:
        raise ScriptError(f"cannot parse {path}: {exc}") from exc
    except OSError as exc:
        raise ScriptError(f"cannot read {path}: {exc}") from exc
    key = root.findtext("ApiKey", "").strip()
    if not key:
        raise ScriptError(f"{path} does not contain an API key")
    return key


class EnvFile:
    """Update simple KEY=value files while preserving comments and ordering."""

    def __init__(self, path: Path):
        self.path = path
        self.lines = (
            path.read_text(encoding="utf-8").splitlines(keepends=True)
            if path.exists()
            else []
        )

    def get(self, key: str, default: str = "") -> str:
        value = default
        prefix = f"{key}="
        for line in self.lines:
            if line.rstrip("\n").startswith(prefix):
                value = line.rstrip("\n").split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value

    def set(self, key: str, value: str) -> bool:
        """Set all existing occurrences, or append the key, and report changes."""
        if "\n" in value or "\r" in value or "\x00" in value:
            raise ScriptError(f"invalid newline or NUL in value for {key}")
        replacement = f"{key}={value}\n"
        prefix = f"{key}="
        changed = False
        found = False
        updated = []
        for line in self.lines:
            if line.rstrip("\n").startswith(prefix):
                found = True
                if line != replacement:
                    changed = True
                updated.append(replacement)
            else:
                updated.append(line)
        if not found:
            updated.append(replacement)
            changed = True
        self.lines = updated
        return changed

    def unset(self, key: str) -> bool:
        """Remove all occurrences of a key and report whether anything changed."""
        prefix = f"{key}="
        updated = [
            line for line in self.lines if not line.rstrip("\n").startswith(prefix)
        ]
        changed = len(updated) != len(self.lines)
        self.lines = updated
        return changed

    def write(self, mode: int = 0o600) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent, text=True
        )
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.writelines(self.lines)
            os.replace(temporary, self.path)
            os.chmod(self.path, mode)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise ScriptError(f"could not write {self.path}: {exc}") from exc


def create_env(example: Path, destination: Path) -> None:
    """Create a private env file from its template, without overwriting it."""
    if destination.is_symlink():
        raise ScriptError(f"refusing to use symlinked environment file {destination}")
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(example, destination)
        except OSError as exc:
            raise ScriptError(f"could not create {destination}: {exc}") from exc
    try:
        os.chmod(destination, 0o600)
    except OSError as exc:
        raise ScriptError(f"could not secure {destination}: {exc}") from exc


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
        os.replace(temporary, path)
        os.chmod(path, mode)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise ScriptError(f"could not write {path}: {exc}") from exc


def run(
    command: Sequence[str], label: str, *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, input=input_text, text=True, check=False)
    except OSError as exc:
        raise ScriptError(f"could not run {label}: {exc}") from exc
    if result.returncode:
        raise ScriptError(f"{label} failed with exit status {result.returncode}")
    return result


def capture(command: Sequence[str], label: str) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ScriptError(f"could not run {label}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise ScriptError(f"{label} failed: {detail[-500:]}")
    return result.stdout.strip()


def detect_tailscale_ipv4() -> str:
    for command in (("tailscale", "ip", "-4"), ("sudo", "-n", "tailscale", "ip", "-4")):
        try:
            value = capture(command, "Tailscale IP detection").splitlines()[0]
            address = ipaddress.ip_address(value)
            if address.version == 4:
                return str(address)
        except (ScriptError, IndexError, ValueError):
            continue
    return ""


def detect_public_ipv4() -> str:
    candidates: list[str] = []
    try:
        output = capture(("ip", "-4", "route", "get", "1.1.1.1"), "public IP detection")
        parts = output.split()
        if "src" in parts:
            candidates.append(parts[parts.index("src") + 1])
    except ScriptError:
        pass
    try:
        output = capture(
            ("ip", "-4", "-o", "addr", "show", "scope", "global"), "public IP detection"
        )
        candidates.extend(part.split("/")[0] for part in output.split() if "/" in part)
    except ScriptError:
        pass
    tailnet = ipaddress.ip_network("100.64.0.0/10")
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if (
            address.version == 4
            and not address.is_loopback
            and not address.is_link_local
            and address not in tailnet
        ):
            return str(address)
    return ""


def require_commands(commands: Iterable[str]) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise ScriptError(f"missing required command(s): {', '.join(missing)}")


HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)
SUBDOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def validate_hostname(value: str, label: str = "hostname") -> str:
    value = value.strip().rstrip(".")
    if not HOSTNAME_RE.fullmatch(value):
        raise ScriptError(f"invalid {label}: {value!r}")
    return value.lower()


def validate_subdomain(value: str, label: str = "subdomain") -> str:
    value = value.strip()
    if not SUBDOMAIN_RE.fullmatch(value):
        raise ScriptError(f"invalid {label}: {value!r}")
    return value.lower()


def redact(value: str) -> str:
    return "<set>" if value else "<empty>"
