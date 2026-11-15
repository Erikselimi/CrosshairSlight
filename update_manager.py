"""Check and stage releases from the public GitHub repository."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from version import APP_VERSION

GITHUB_OWNER = "Erikselimi"
GITHUB_REPO = "CrosshairSlight"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
MAX_UPDATE_BYTES = 250 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class UpdateError(RuntimeError):
    """An update could not be checked, downloaded, or staged."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    download_url: str
    size: int
    sha256: str | None


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise UpdateError(f"Release version {value!r} must use a tag such as v1.2.3.")
    return tuple(int(component) for component in match.groups())


def release_update(payload: object, current_version: str = APP_VERSION) -> UpdateInfo | None:
    if not isinstance(payload, dict):
        raise UpdateError("The GitHub release response was invalid.")
    tag = payload.get("tag_name")
    assets = payload.get("assets")
    if not isinstance(tag, str) or not isinstance(assets, list):
        raise UpdateError("The GitHub release is missing its version or assets.")
    latest_version = parse_version(tag.removeprefix("v"))
    if latest_version <= parse_version(current_version):
        return None

    asset = next((item for item in assets if isinstance(item, dict) and item.get("name") == "Sightline.exe"), None)
    if asset is None:
        raise UpdateError(f"Release {tag} has no Sightline.exe asset.")
    download_url = asset.get("browser_download_url")
    size = asset.get("size")
    if not isinstance(download_url, str) or not isinstance(size, int) or isinstance(size, bool):
        raise UpdateError(f"Release {tag} has invalid Sightline.exe metadata.")
    parsed_url = urlparse(download_url)
    expected_prefix = f"/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/"
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com" or not parsed_url.path.startswith(expected_prefix):
        raise UpdateError("The release download URL did not match the configured GitHub project.")
    if not 1 <= size <= MAX_UPDATE_BYTES:
        raise UpdateError("The release executable has an unsupported file size.")
    digest = asset.get("digest")
    if digest is not None:
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise UpdateError("The release executable has an unsupported checksum.")
        sha256 = digest.removeprefix("sha256:").casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise UpdateError("The release executable has an invalid SHA-256 checksum.")
    else:
        sha256 = None
    return UpdateInfo(tag.removeprefix("v"), tag, download_url, size, sha256)


def check_for_update(timeout: float = 10.0) -> UpdateInfo | None:
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Sightline/{APP_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(1_000_001).decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError("No public GitHub release was found for this project.") from error
        raise UpdateError(f"GitHub update check failed with HTTP {error.code}.") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError(f"Could not check GitHub for updates: {error}") from error
    return release_update(payload)


def download_update(update: UpdateInfo, destination_directory: Path) -> Path:
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UpdateError(f"Could not prepare the update folder: {error}") from error
    request = urllib.request.Request(update.download_url, headers={"User-Agent": f"Sightline/{APP_VERSION}"})
    temporary_path: Path | None = None
    digest = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise UpdateError("The release download redirected to a non-HTTPS URL.")
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination_directory, suffix=".download", delete=False
            ) as output:
                temporary_path = Path(output.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > update.size or received > MAX_UPDATE_BYTES:
                        raise UpdateError("The downloaded executable exceeded its published size.")
                    digest.update(chunk)
                    output.write(chunk)
        if received != update.size:
            raise UpdateError("The downloaded executable size did not match the GitHub release.")
        if update.sha256 is not None and digest.hexdigest() != update.sha256:
            raise UpdateError("The downloaded executable failed its SHA-256 check.")
        staged_path = destination_directory / f"Sightline-{update.version}.new.exe"
        os.replace(temporary_path, staged_path)
        return staged_path
    except (OSError, urllib.error.URLError) as error:
        raise UpdateError(f"Could not download the update: {error}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def launch_update_installer(staged_executable: Path, running_executable: Path, log_path: Path) -> None:
    if os.name != "nt":
        raise UpdateError("Automatic installation is supported on Windows only.")
    if not staged_executable.is_file() or not running_executable.is_file():
        raise UpdateError("The staged update or current executable could not be found.")
    script_path = staged_executable.with_suffix(".update.ps1")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UpdateError(f"Could not prepare the update log folder: {error}") from error

    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    script = f"""$ErrorActionPreference = 'Stop'
$processId = {os.getpid()}
$source = {quote(str(staged_executable))}
$target = {quote(str(running_executable))}
$log = {quote(str(log_path))}
$backup = "$target.sightline-backup"
try {{
    while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 400 }}
    if (Test-Path -LiteralPath $target) {{ Move-Item -LiteralPath $target -Destination $backup -Force }}
    try {{
        Move-Item -LiteralPath $source -Destination $target -Force
        Start-Process -FilePath $target
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }} catch {{
        if (Test-Path -LiteralPath $target) {{ Remove-Item -LiteralPath $target -Force }}
        if (Test-Path -LiteralPath $backup) {{ Move-Item -LiteralPath $backup -Destination $target -Force }}
        throw
    }}
}} catch {{
    [System.IO.File]::AppendAllText($log, [DateTime]::Now.ToString('s') + ' ' + ($_ | Out-String) + [Environment]::NewLine)
}}
"""
    try:
        script_path.write_text(script, encoding="utf-8-sig")
    except OSError as error:
        raise UpdateError(f"Could not prepare the update installer: {error}") from error
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(script_path)],
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as error:
        raise UpdateError(f"Could not start the update installer: {error}") from error
