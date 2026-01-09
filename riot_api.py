from __future__ import annotations
from typing import Dict, Any, List, Optional
import requests
from urllib.parse import quote


# Platform routing (for Summoner-V4, League-V4)
# Regional routing (for Match-V5) is a cluster: americas / europe / asia / sea
PLATFORM_TO_REGIONAL = {
    # Americas cluster
    "NA1": "americas",
    "BR1": "americas",
    "LA1": "americas",
    "LA2": "americas",
    "OC1": "americas",
    # Europe cluster
    "EUW1": "europe",
    "EUN1": "europe",
    "TR1": "europe",
    "RU": "europe",
    # Asia cluster
    "KR": "asia",
    "JP1": "asia",
    # SEA cluster (if applicable to your account routing; some endpoints vary)
    "SG2": "sea",
    "PH2": "sea",
    "TH2": "sea",
    "TW2": "sea",
    "VN2": "sea",
}

def _riot_get(url: str, api_key: str) -> Any:
    headers = {"X-Riot-Token": api_key}
    r = requests.get(url, headers=headers, timeout=10)

    # If Riot returns an error JSON, include it in the exception
    if not r.ok:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text}
        raise RuntimeError(f"Riot API {r.status_code} for {url} -> {err}")

    return r.json()


def get_summoner_by_puuid(platform: str, api_key: str, puuid: str) -> Dict[str, Any]:
    platform = platform.lower()
    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    return _riot_get(url, api_key)

def get_league_entries(platform: str, api_key: str, summoner_id: str) -> List[Dict[str, Any]]:
    platform = platform.lower()
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    return _riot_get(url, api_key)

def get_match_ids_by_puuid(regional: str, api_key: str, puuid: str, queue: int = 420, count: int = 10) -> List[str]:
    # queue=420 is Ranked Solo/Duo
    url = f"https://{regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={queue}&count={count}"
    return _riot_get(url, api_key)

def get_match(regional: str, api_key: str, match_id: str) -> Dict[str, Any]:
    url = f"https://{regional}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return _riot_get(url, api_key)

def pick_platform_from_region(region_locale_payload: Dict[str, Any]) -> Optional[str]:
    """
    LCU /riotclient/region-locale returns something like:
      { "region": "EUW", "locale": "en_GB", ... }
    Riot API platform is typically EUW1 / EUN1 / NA1 etc.
    We'll map common regions here.
    """
    region = (region_locale_payload.get("region") or "").upper()

    region_map = {
        "EUW": "EUW1",
        "EUNE": "EUN1",
        "NA": "NA1",
        "BR": "BR1",
        "LAN": "LA1",
        "LAS": "LA2",
        "OCE": "OC1",
        "KR": "KR",
        "JP": "JP1",
        "TR": "TR1",
        "RU": "RU",
        # SEA variants (may differ by account/provider)
        "SG": "SG2",
        "PH": "PH2",
        "TH": "TH2",
        "TW": "TW2",
        "VN": "VN2",
    }
    return region_map.get(region)

def platform_to_regional(platform: str) -> str:
    return PLATFORM_TO_REGIONAL.get(platform, "europe")

def get_account_by_riot_id(regional: str, api_key: str, game_name: str, tag_line: str) -> Dict[str, Any]:
    gn = quote(game_name, safe="")
    tl = quote(tag_line, safe="")
    url = f"https://{regional}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gn}/{tl}"
    return _riot_get(url, api_key)

def get_summoner_by_name(platform: str, api_key: str, summoner_name: str) -> Dict[str, Any]:
    platform = platform.lower()
    name = quote(summoner_name, safe="")
    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name}"
    return _riot_get(url, api_key)