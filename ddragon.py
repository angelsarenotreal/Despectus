from __future__ import annotations
from typing import Dict
import requests

def get_latest_version() -> str:
    versions = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
    return versions[0]

def get_champion_id_map(version: str) -> Dict[int, Dict[str, str]]:
    """
    Returns mapping: championKey(int) -> { "name": str, "id": str }
    """
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    data = requests.get(url, timeout=10).json()["data"]
    out: Dict[int, Dict[str, str]] = {}
    for champ_name, champ in data.items():
        key = int(champ["key"])
        out[key] = {"name": champ["name"], "id": champ["id"]}
    return out

def profile_icon_url(version: str, icon_id: int) -> str:
    return f"https://ddragon.leagueoflegends.com/cdn/{version}/img/profileicon/{icon_id}.png"

def champ_icon_url(version: str, champ_id: str) -> str:
    return f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champ_id}.png"

def rank_emblem_url(tier: str) -> str:
    """
    Rank emblems come from Riot's client assets (CommunityDragon mirror).
    tier examples: IRON, BRONZE, SILVER, GOLD, PLATINUM, EMERALD, DIAMOND, MASTER, GRANDMASTER, CHALLENGER
    """
    t = (tier or "UNRANKED").upper()

    # CommunityDragon uses "PLATINUM", "GRANDMASTER" etc.
    known = {
        "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
        "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"
    }
    if t not in known:
        # If unranked, show a generic icon (we'll reuse iron as fallback)
        t = "IRON"

    return (
        "https://raw.communitydragon.org/latest/plugins/"
        "rcp-fe-lol-shared-components/global/default/images/"
        f"ranked-emblems/{t.lower()}.png"
    )
