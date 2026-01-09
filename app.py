from __future__ import annotations

import math
from typing import Optional, List, Dict, Any
from collections import Counter

from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit
from PySide6.QtCore import QTimer

from settings import load_settings, save_api_key_to_appdata
from lcu import (
    read_lockfile,
    get_current_summoner,
    get_region_locale,
    get_chat_me,
    get_ranked_stats,
)
from riot_api import (
    pick_platform_from_region,
    platform_to_regional,
    get_account_by_riot_id,
    get_match_ids_by_puuid,
    get_match,
)
from ddragon import (
    get_latest_version,
    get_champion_id_map,
    profile_icon_url,
    champ_icon_url,
    rank_emblem_url,
)
from model import RankedSnapshot, MatchRow
from ui_main import MainWindow


def next_rank_label(tier: str, div: str) -> Optional[str]:
    tier = (tier or "").upper()
    div = (div or "").upper()

    if tier == "MASTER":
        return "Grandmaster"
    if tier == "GRANDMASTER":
        return "Challenger"
    if tier == "CHALLENGER":
        return None

    tiers = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
    divs = ["IV", "III", "II", "I"]

    if tier not in tiers or div not in divs:
        return None

    idx = divs.index(div)
    if idx > 0:
        return f"{tier.title()} {divs[idx-1]}"
    else:
        if tier == "DIAMOND":
            return "Master"
        next_tier = tiers[tiers.index(tier) + 1]
        return f"{next_tier.title()} IV"


def pick_soloq_from_lcu_ranked(ranked_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not ranked_payload:
        return None

    queues = ranked_payload.get("queues") or ranked_payload.get("queueMap") or []
    if isinstance(queues, dict):
        queues = list(queues.values())

    for q in queues:
        if q.get("queueType") == "RANKED_SOLO_5x5":
            return q
    return None


def build_match_row(
    match: Dict[str, Any],
    puuid: str,
    champ_map: Dict[int, Dict[str, str]],
    dd_version: str,
) -> Optional[MatchRow]:
    info = match.get("info", {})
    participants = info.get("participants", [])
    me = None
    for p in participants:
        if p.get("puuid") == puuid:
            me = p
            break
    if not me:
        return None

    champ_key = int(me.get("championId", 0))
    champ_meta = champ_map.get(champ_key, {})
    champ_name = champ_meta.get("name", f"Champion {champ_key}")
    champ_id = champ_meta.get("id", "")
    icon = champ_icon_url(dd_version, champ_id) if champ_id else ""

    duration_sec = int(info.get("gameDuration", 0))
    duration_min = max(1, duration_sec // 60)

    return MatchRow(
        match_id=match.get("metadata", {}).get("matchId", "—"),
        win=bool(me.get("win", False)),
        champion_name=champ_name,
        champ_icon_url=icon,
        k=int(me.get("kills", 0)),
        d=int(me.get("deaths", 0)),
        a=int(me.get("assists", 0)),
        cs=int(me.get("totalMinionsKilled", 0)) + int(me.get("neutralMinionsKilled", 0)),
        vision=int(me.get("visionScore", 0)),
        duration_min=duration_min,
    )


def main():
    settings = load_settings()

    app = QApplication([])
    win = MainWindow()
    win.apply_theme()
    win.show()

    #   settings.refresh_seconds = 300  # 5 min auto refresh (you can disable later if you want)
    if not settings.riot_api_key:
        key, ok = QInputDialog.getText(
            win,
            "Riot API Key Required",
            "Paste your RIOT_API_KEY (stored in %APPDATA%\\Despectus\\.env):",
            QLineEdit.Password,
            ""
        )
    if ok and key.strip():
        save_api_key_to_appdata(key.strip())
        settings = load_settings()
    else:
        win.set_status("Missing RIOT_API_KEY. Please add it to %APPDATA%\\Despectus\\.env")

    dd_version = get_latest_version()
    champ_map = get_champion_id_map(dd_version)

    win.set_avg_lp(settings.avg_lp_per_win)

    last_rank_state = {"ranked_obj": None, "next_label": None}
    state = {"last_riot_id": None}

    def recompute_est_only():
        ranked_obj = last_rank_state["ranked_obj"]
        next_label = last_rank_state["next_label"]
        if ranked_obj:
            est = max(1, math.ceil(100 / max(1, int(settings.avg_lp_per_win))))
            win.set_ranked(ranked_obj, next_label, est)
        else:
            win.set_ranked(None, None, None)

    def on_avg_lp_change(v: int):
        settings.avg_lp_per_win = int(v)
        recompute_est_only()

    win.set_avg_lp_callback(on_avg_lp_change)

    def refresh():
        auth = read_lockfile()
        if not auth:
            win.set_status("League Client not detected (start the client).")
            return

        region_locale = get_region_locale(auth) or {}
        platform = pick_platform_from_region(region_locale)
        if not platform:
            win.set_status("Client detected, but region unknown.")
            return

        current = get_current_summoner(auth)
        if not current:
            win.set_status("Client detected, but not logged in.")
            return

        me = get_chat_me(auth)
        if not me:
            win.set_status("Client detected, but Riot ID not available yet.")
            return

        game_name = me.get("gameName")
        tag_line = me.get("gameTag") or me.get("tagLine")
        if not game_name or not tag_line:
            win.set_status("Logged in, but Riot ID missing (gameName/tagLine).")
            return

        riot_id = f"{game_name}#{tag_line}"

        display_name = current.get("displayName", game_name)
        level = int(current.get("summonerLevel", 0))
        icon_id = int(current.get("profileIconId", 0))
        win.set_profile(display_name, riot_id, level, profile_icon_url(dd_version, icon_id))

        ranked_payload = get_ranked_stats(auth) or {}
        solo = pick_soloq_from_lcu_ranked(ranked_payload)

        ranked_obj: Optional[RankedSnapshot] = None
        next_label: Optional[str] = None
        est: Optional[int] = None

        if solo:
            tier = str(solo.get("tier", "UNRANKED")).upper()
            div = str(solo.get("division", "—")).upper()
            lp = int(solo.get("leaguePoints", 0))
            wins = int(solo.get("wins", 0))
            losses = int(solo.get("losses", 0))

            if tier in {"NA", "NONE", "UNRANKED"}:
                tier = "UNRANKED"

            if tier != "UNRANKED":
                ranked_obj = RankedSnapshot(
                    queue="RANKED_SOLO_5x5",
                    tier=tier,
                    rank=div,
                    lp=lp,
                    wins=wins,
                    losses=losses,
                )
                next_label = next_rank_label(tier, div)
                est = max(1, math.ceil(100 / max(1, int(settings.avg_lp_per_win))))

        win.set_ranked(ranked_obj, next_label, est)
        last_rank_state["ranked_obj"] = ranked_obj
        last_rank_state["next_label"] = next_label

        if ranked_obj:
            win.set_rank_emblem(rank_emblem_url(ranked_obj.tier))
        else:
            win.clear_rank_emblem()

        if not settings.riot_api_key:
            win.set_status(f"Connected: {platform} • {riot_id} • Missing RIOT_API_KEY")
            return

        try:
            regional = platform_to_regional(platform)
            acct = get_account_by_riot_id(regional, settings.riot_api_key, game_name, tag_line)
            public_puuid = acct.get("puuid")
            if not public_puuid:
                win.set_status(f"Account lookup failed for {riot_id}")
                return

            match_ids = get_match_ids_by_puuid(
                regional,
                settings.riot_api_key,
                public_puuid,
                queue=420,
                count=10,
            )

            rows: List[MatchRow] = []
            for mid in match_ids:
                m = get_match(regional, settings.riot_api_key, mid)
                row = build_match_row(m, public_puuid, champ_map, dd_version)
                if row:
                    rows.append(row)

            win.set_matches(rows)

            if rows:
                wins10 = sum(1 for r in rows if r.win)
                losses10 = len(rows) - wins10
                wr10 = (wins10 / len(rows)) * 100.0
                avg_kda = sum(((r.k + r.a) / max(1, r.d)) for r in rows) / len(rows)

                avg_cs = sum(r.cs for r in rows) / len(rows)
                avg_dur = sum(r.duration_min for r in rows) / len(rows)
                best_kda = max(((r.k + r.a) / max(1, r.d)) for r in rows)

                win.set_recent_stats(wr10, avg_kda)
                win.set_extra_stats(wins10, losses10, avg_cs, avg_dur, best_kda)

                counts = Counter((r.champion_name, r.champ_icon_url) for r in rows)
                top3 = counts.most_common(3)
                champs_payload = [(n, i, c) for ((n, i), c) in top3]
                win.set_top_champs(champs_payload)
            else:
                win.set_recent_stats(None, None)
                win.set_extra_stats(None, None, None, None, None)
                win.set_top_champs([])

            win.set_status(f"Connected: {platform} • {riot_id}")
            state["last_riot_id"] = riot_id

        except Exception as e:
            win.set_status(str(e))
            return

    win.set_refresh_callback(refresh)

    watch = QTimer()
    watch.setInterval(2500)

    def check_account_swap():
        auth = read_lockfile()
        if not auth:
            return
        me = get_chat_me(auth)
        if not me:
            return
        gn = me.get("gameName")
        tl = me.get("gameTag") or me.get("tagLine")
        if not gn or not tl:
            return
        rid = f"{gn}#{tl}"
        if state.get("last_riot_id") and rid != state["last_riot_id"]:
            refresh()

    watch.timeout.connect(check_account_swap)
    watch.start()

    QTimer.singleShot(150, refresh)
    app.exec()


if __name__ == "__main__":
    main()
