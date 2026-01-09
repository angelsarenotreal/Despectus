from __future__ import annotations
import base64
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import psutil
import requests

requests.packages.urllib3.disable_warnings()  # self-signed cert in LCU


@dataclass
class LcuAuth:
    port: int
    password: str
    protocol: str = "https"

    @property
    def base_url(self) -> str:
        return f"{self.protocol}://127.0.0.1:{self.port}"

    @property
    def basic_auth_header(self) -> str:
        token = base64.b64encode(f"riot:{self.password}".encode("utf-8")).decode("utf-8")
        return f"Basic {token}"


def _find_league_process() -> Optional[psutil.Process]:
    """
    On Windows, the modern client is usually LeagueClientUx.exe.
    We'll try a few names.
    """
    candidates = {"LeagueClientUx.exe", "LeagueClient.exe"}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            if p.info["name"] in candidates:
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _lockfile_path_from_process(proc: psutil.Process) -> Optional[str]:
    """
    lockfile is typically in the same directory as LeagueClient.exe.
    LeagueClientUx.exe often lives in a subfolder like ...\\RADS\\...; but usually
    the lockfile is in the main League of Legends install folder.

    We'll attempt:
    - directory of proc exe
    - parent directories (a few levels up)
    """
    try:
        exe_path = proc.exe()
    except Exception:
        return None

    # try current dir and parents up to 5 levels
    cur = os.path.dirname(exe_path)
    for _ in range(6):
        candidate = os.path.join(cur, "lockfile")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def read_lockfile() -> Optional[LcuAuth]:
    """
    lockfile format (colon-separated):
      processName:pid:port:password:protocol
    """
    proc = _find_league_process()
    if not proc:
        return None

    lockfile = _lockfile_path_from_process(proc)
    if not lockfile or not os.path.exists(lockfile):
        return None

    try:
        raw = open(lockfile, "r", encoding="utf-8").read().strip()
        parts = raw.split(":")
        if len(parts) < 5:
            return None
        port = int(parts[2])
        password = parts[3]
        protocol = parts[4]
        return LcuAuth(port=port, password=password, protocol=protocol)
    except Exception:
        return None


def lcu_get(auth: LcuAuth, path: str) -> Dict[str, Any]:
    url = auth.base_url + path
    headers = {"Authorization": auth.basic_auth_header}
    r = requests.get(url, headers=headers, verify=False, timeout=5)
    r.raise_for_status()
    return r.json()


def get_current_summoner(auth: LcuAuth) -> Optional[Dict[str, Any]]:
    try:
        return lcu_get(auth, "/lol-summoner/v1/current-summoner")
    except Exception:
        return None


def get_region_locale(auth: LcuAuth) -> Optional[Dict[str, Any]]:
    try:
        return lcu_get(auth, "/riotclient/region-locale")
    except Exception:
        return None


def wait_for_client(timeout_sec: int = 60) -> Optional[LcuAuth]:
    start = time.time()
    while time.time() - start < timeout_sec:
        auth = read_lockfile()
        if auth:
            return auth
        time.sleep(1)
    return None

def get_chat_me(auth: LcuAuth) -> Optional[Dict[str, Any]]:
    """
    Returns Riot ID info when logged in:
      { "gameName": "...", "gameTag": "EUW", ... }
    """
    try:
        return lcu_get(auth, "/lol-chat/v1/me")
    except Exception:
        return None

def get_ranked_stats(auth: LcuAuth):
    """
    Returns ranked stats for the logged-in player from the client.
    Includes Solo/Duo tier/division/LP/wins/losses.
    """
    try:
        return lcu_get(auth, "/lol-ranked/v1/current-ranked-stats")
    except Exception:
        return None
