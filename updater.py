from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import re
import tempfile
import requests
import subprocess
import os


GITHUB_API = "https://api.github.com"


@dataclass
class UpdateInfo:
    latest_version: str   # e.g. "1.2.0"
    asset_name: str       # e.g. "Despectus-Setup.exe"
    asset_url: str        # browser_download_url
    page_url: str         # html_url


def _normalize_version(tag: str) -> str:
    # accepts "v1.2.0" or "1.2.0"
    tag = (tag or "").strip()
    if tag.lower().startswith("v"):
        tag = tag[1:]
    return tag


def _parse_semver(v: str) -> Tuple[int, int, int]:
    v = _normalize_version(v)
    m = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)\s*$", v)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer(latest: str, current: str) -> bool:
    return _parse_semver(latest) > _parse_semver(current)


def fetch_latest_release(owner: str, repo: str, timeout: int = 10) -> Dict[str, Any]:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Despectus-Updater",
        },
    )
    r.raise_for_status()
    return r.json()


def pick_installer_asset(release_json: Dict[str, Any], preferred_name_contains: str = "Setup") -> Optional[UpdateInfo]:
    tag = release_json.get("tag_name") or ""
    html_url = release_json.get("html_url") or ""
    latest_version = _normalize_version(tag)

    assets = release_json.get("assets") or []
    if not assets:
        return None

    # Prefer an .exe containing "Setup" in name
    candidates = []
    for a in assets:
        name = (a.get("name") or "")
        url = (a.get("browser_download_url") or "")
        if not name.lower().endswith(".exe"):
            continue
        if not url:
            continue
        candidates.append((name, url))

    if not candidates:
        return None

    preferred = [c for c in candidates if preferred_name_contains.lower() in c[0].lower()]
    name, url = (preferred[0] if preferred else candidates[0])

    return UpdateInfo(
        latest_version=latest_version,
        asset_name=name,
        asset_url=url,
        page_url=html_url,
    )


def download_file(url: str, timeout: int = 60) -> Optional[str]:
    try:
        r = requests.get(
            url,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "Despectus-Updater"},
        )
        r.raise_for_status()

        tmp_dir = Path(tempfile.gettempdir())
        out = tmp_dir / Path(url).name
        if out.suffix.lower() != ".exe":
            out = tmp_dir / "Despectus-Setup.exe"

        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)

        return str(out)
    except Exception:
        return None


def run_installer(installer_path: str, silent: bool = False):
    """
    Launch the installer. You MUST quit the app after calling this.
    """
    p = Path(installer_path)
    if not p.exists():
        return

    # Inno Setup supports /SILENT and /VERYSILENT, but if you want a normal UX, keep silent=False
    args = [str(p)]
    if silent:
        args += ["/SILENT"]

    # Use shell=False, detached, no wait
    try:
        subprocess.Popen(args, close_fds=True)
    except Exception:
        # fallback
        os.startfile(str(p))  # type: ignore[attr-defined]
