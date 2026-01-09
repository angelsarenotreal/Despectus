from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def appdata_env_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # Fallback: local
        return Path(".env")
    return Path(appdata) / "Despectus" / ".env"


@dataclass
class AppSettings:
    riot_api_key: str
    avg_lp_per_win: int = 22
    refresh_seconds: int = 300


def load_settings() -> AppSettings:
    # 1) Load AppData env first (installed app)
    env_path = appdata_env_path()
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        # 2) Fall back to local .env (dev mode)
        load_dotenv(".env", override=True)

    riot_key = os.getenv("RIOT_API_KEY", "").strip()
    avg_lp = int(os.getenv("AVG_LP_PER_WIN", "22"))
    refresh = int(os.getenv("REFRESH_SECONDS", "300"))

    return AppSettings(
        riot_api_key=riot_key,
        avg_lp_per_win=avg_lp,
        refresh_seconds=refresh,
    )


def save_api_key_to_appdata(key: str) -> Path:
    """
    Writes/updates RIOT_API_KEY inside %APPDATA%\\Despectus\\.env
    preserving other values if present.
    """
    key = (key or "").strip()
    env_path = appdata_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    existing["RIOT_API_KEY"] = key
    if "AVG_LP_PER_WIN" not in existing:
        existing["AVG_LP_PER_WIN"] = "22"
    if "REFRESH_SECONDS" not in existing:
        existing["REFRESH_SECONDS"] = "300"

    text = "\n".join([f"{k}={v}" for k, v in existing.items()]) + "\n"
    env_path.write_text(text, encoding="utf-8")
    return env_path
