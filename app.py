from __future__ import annotations

import math
from typing import Optional, List, Dict, Any, Tuple
from collections import Counter

import requests
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)
from PySide6.QtCore import QTimer, QObject, Signal, QThread, Qt

from settings import load_settings, save_api_key_to_appdata
from lcu import read_lockfile, get_current_summoner, get_region_locale, get_chat_me, get_ranked_stats
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

from updater import fetch_latest_release, pick_installer_asset, is_newer, download_file, run_installer


# =========================
# CONFIG (EDIT THESE)
# =========================
APP_VERSION = "1.0.2"      # must match your installed version/tag
GITHUB_OWNER = "angelsarenotreal"         # e.g. "yourgithubname"
GITHUB_REPO = "Despectus"          # e.g. "Despectus"
# =========================


# -----------------------
# Dispatcher: guarantees code runs on UI thread
# -----------------------
class Dispatcher(QObject):
    run = Signal(object)  # callable

    def __init__(self):
        super().__init__()
        self.run.connect(self._exec, Qt.QueuedConnection)

    def _exec(self, fn):
        try:
            fn()
        except Exception as e:
            # Avoid crashing UI thread silently
            print("UI-dispatch error:", e)


# -----------------------
# Rank helpers
# -----------------------
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
    divs = ["IV", "III", "II", "I"]  # promotion is IV -> III -> II -> I

    if tier not in tiers or div not in divs:
        return None

    idx = divs.index(div)

    # FIX: III -> II, II -> I
    if idx < len(divs) - 1:
        return f"{tier.title()} {divs[idx + 1]}"

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


def ensure_api_key(win: MainWindow):
    settings = load_settings()
    if settings.riot_api_key:
        return settings

    key, accepted = QInputDialog.getText(
        win,
        "Riot API Key Required",
        "Paste your RIOT_API_KEY (stored in %APPDATA%\\Despectus\\.env):",
        QLineEdit.Password,
        ""
    )

    if accepted and key.strip():
        save_api_key_to_appdata(key.strip())
        return load_settings()

    win.set_status("Missing RIOT_API_KEY. You can add it in %APPDATA%\\Despectus\\.env")
    return settings


def estimate_games_to_next(lp: int, avg_lp_gain: int) -> int:
    avg = max(1, int(avg_lp_gain))
    needed = max(0, 100 - int(lp))
    return max(1, math.ceil(needed / avg))


# -----------------------
# Worker: fetch matches + images without freezing UI
# -----------------------
class RefreshWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        *,
        riot_api_key: str,
        regional: str,
        game_name: str,
        tag_line: str,
        dd_version: str,
        champ_map: Dict[int, Dict[str, str]],
        profile_icon_url_str: str,
        emblem_url_str: str,
    ):
        super().__init__()
        self.riot_api_key = riot_api_key
        self.regional = regional
        self.game_name = game_name
        self.tag_line = tag_line
        self.dd_version = dd_version
        self.champ_map = champ_map
        self.profile_icon_url_str = profile_icon_url_str
        self.emblem_url_str = emblem_url_str
        self._img_cache: Dict[str, bytes] = {}

    def _get_bytes(self, url: str) -> bytes:
        if not url:
            return b""
        if url in self._img_cache:
            return self._img_cache[url]
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Despectus/1.0"})
            r.raise_for_status()
            raw = r.content
            self._img_cache[url] = raw
            return raw
        except Exception:
            return b""

    def _build_match_row(self, match: Dict[str, Any], puuid: str) -> Optional[MatchRow]:
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
        champ_meta = self.champ_map.get(champ_key, {})
        champ_name = champ_meta.get("name", f"Champion {champ_key}")
        champ_id = champ_meta.get("id", "")

        icon_url = champ_icon_url(self.dd_version, champ_id) if champ_id else ""
        icon_bytes = self._get_bytes(icon_url)

        duration_sec = int(info.get("gameDuration", 0))
        duration_min = max(1, duration_sec // 60)

        return MatchRow(
            match_id=match.get("metadata", {}).get("matchId", "—"),
            win=bool(me.get("win", False)),
            champion_name=champ_name,
            champ_icon_bytes=icon_bytes,
            k=int(me.get("kills", 0)),
            d=int(me.get("deaths", 0)),
            a=int(me.get("assists", 0)),
            cs=int(me.get("totalMinionsKilled", 0)) + int(me.get("neutralMinionsKilled", 0)),
            vision=int(me.get("visionScore", 0)),
            duration_min=duration_min,
        )

    def run(self):
        try:
            profile_bytes = self._get_bytes(self.profile_icon_url_str)
            emblem_bytes = self._get_bytes(self.emblem_url_str)

            acct = get_account_by_riot_id(self.regional, self.riot_api_key, self.game_name, self.tag_line)
            puuid = acct.get("puuid")
            if not puuid:
                self.failed.emit("Account lookup failed (no PUUID).")
                return

            match_ids = get_match_ids_by_puuid(self.regional, self.riot_api_key, puuid, queue=420, count=10)

            rows: List[MatchRow] = []
            for mid in match_ids:
                m = get_match(self.regional, self.riot_api_key, mid)
                row = self._build_match_row(m, puuid)
                if row:
                    rows.append(row)

            champs_payload: List[Tuple[str, bytes, int]] = []
            if rows:
                counts = Counter(r.champion_name for r in rows)
                top3 = counts.most_common(3)
                for champ_name, c in top3:
                    icon_bytes = next((r.champ_icon_bytes for r in rows if r.champion_name == champ_name), b"")
                    champs_payload.append((champ_name, icon_bytes, c))

                wins10 = sum(1 for r in rows if r.win)
                losses10 = len(rows) - wins10
                wr10 = (wins10 / len(rows)) * 100.0
                avg_kda = sum(((r.k + r.a) / max(1, r.d)) for r in rows) / len(rows)
                avg_cs = sum(r.cs for r in rows) / len(rows)
                avg_dur = sum(r.duration_min for r in rows) / len(rows)
                best_kda = max(((r.k + r.a) / max(1, r.d)) for r in rows)
            else:
                wins10 = losses10 = None
                wr10 = avg_kda = None
                avg_cs = avg_dur = best_kda = None

            self.finished.emit({
                "profile_bytes": profile_bytes,
                "emblem_bytes": emblem_bytes,
                "rows": rows,
                "top_champs": champs_payload,
                "wins10": wins10,
                "losses10": losses10,
                "wr10": wr10,
                "avg_kda": avg_kda,
                "avg_cs": avg_cs,
                "avg_dur": avg_dur,
                "best_kda": best_kda,
            })

        except Exception as e:
            self.failed.emit(str(e))


# -----------------------
# Worker: update check + download
# -----------------------
class UpdateWorker(QObject):
    done = Signal(object)       # UpdateInfo | None
    failed = Signal(str)

    def __init__(self, owner: str, repo: str, current_version: str):
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.current_version = current_version

    def run(self):
        try:
            rel = fetch_latest_release(self.owner, self.repo, timeout=10)
            info = pick_installer_asset(rel, preferred_name_contains="Setup")
            if not info:
                self.done.emit(None)
                return
            if not is_newer(info.latest_version, self.current_version):
                self.done.emit(None)
                return
            self.done.emit(info)
        except Exception as e:
            self.failed.emit(str(e))


class DownloadUpdateWorker(QObject):
    done = Signal(object)       # installer path | None
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            path = download_file(self.url, timeout=60)
            self.done.emit(path)
        except Exception as e:
            self.failed.emit(str(e))


def main():
    app = QApplication([])
    win = MainWindow()
    win.apply_theme()
    win.show()

    dispatcher = Dispatcher()

    # keep references (prevents GC)
    win._threads: List[object] = []

    def track(*objs: object):
        for o in objs:
            win._threads.append(o)

    def stop_thread(t: QThread):
        if t.isRunning():
            t.quit()
            t.wait(2000)

    app.aboutToQuit.connect(lambda: [stop_thread(o) for o in win._threads if isinstance(o, QThread)])

    settings = ensure_api_key(win)

    dd_version = get_latest_version()
    champ_map = get_champion_id_map(dd_version)

    win.set_avg_lp(settings.avg_lp_per_win)

    last_rank_state = {"ranked_obj": None, "next_label": None}
    state = {"last_riot_id": None}

    refresh_thread: Optional[QThread] = None

    def recompute_est_only():
        ranked_obj = last_rank_state["ranked_obj"]
        next_label = last_rank_state["next_label"]
        if ranked_obj:
            est = estimate_games_to_next(ranked_obj.lp, settings.avg_lp_per_win)
            win.set_ranked(ranked_obj, next_label, est)
        else:
            win.set_ranked(None, None, None)

    def on_avg_lp_change(v: int):
        settings.avg_lp_per_win = int(v)
        recompute_est_only()

    win.set_avg_lp_callback(on_avg_lp_change)

    def refresh():
        nonlocal refresh_thread

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

        ranked_payload = get_ranked_stats(auth) or {}
        solo = pick_soloq_from_lcu_ranked(ranked_payload)

        ranked_obj: Optional[RankedSnapshot] = None
        next_label: Optional[str] = None
        est: Optional[int] = None
        emblem_url_str = ""

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
                est = estimate_games_to_next(lp, settings.avg_lp_per_win)
                emblem_url_str = rank_emblem_url(tier)

        win.set_ranked(ranked_obj, next_label, est)
        last_rank_state["ranked_obj"] = ranked_obj
        last_rank_state["next_label"] = next_label

        if not settings.riot_api_key:
            win.set_profile(display_name, riot_id, level, b"")
            win.clear_rank_emblem()
            win.set_status(f"Connected: {platform} • {riot_id} • Missing RIOT_API_KEY")
            return

        if refresh_thread and refresh_thread.isRunning():
            win.set_status(f"Connected: {platform} • {riot_id} • Refresh already running…")
            return

        profile_url_str = profile_icon_url(dd_version, icon_id)
        regional = platform_to_regional(platform)

        win.set_status(f"Connected: {platform} • {riot_id} • Loading…")

        worker = RefreshWorker(
            riot_api_key=settings.riot_api_key,
            regional=regional,
            game_name=game_name,
            tag_line=tag_line,
            dd_version=dd_version,
            champ_map=champ_map,
            profile_icon_url_str=profile_url_str,
            emblem_url_str=emblem_url_str,
        )

        refresh_thread = QThread()
        worker.moveToThread(refresh_thread)
        track(refresh_thread, worker)

        # IMPORTANT: never touch UI in worker thread — dispatch to UI thread
        worker.finished.connect(lambda payload: dispatcher.run.emit(lambda: _on_refresh_finished(payload, platform, riot_id, display_name, level)), Qt.QueuedConnection)
        worker.failed.connect(lambda msg: dispatcher.run.emit(lambda: _on_refresh_failed(msg)), Qt.QueuedConnection)
        refresh_thread.started.connect(worker.run)
        refresh_thread.finished.connect(worker.deleteLater)
        refresh_thread.start()

        state["last_riot_id"] = riot_id

    def _on_refresh_finished(payload: dict, platform: str, riot_id: str, display_name: str, level: int):
        nonlocal refresh_thread

        win.set_profile(display_name, riot_id, level, payload.get("profile_bytes") or b"")

        emblem_bytes = payload.get("emblem_bytes") or b""
        if emblem_bytes:
            win.set_rank_emblem_bytes(emblem_bytes)
        else:
            win.clear_rank_emblem()

        rows: List[MatchRow] = payload.get("rows") or []
        win.set_matches(rows)

        win.set_recent_stats(payload.get("wr10"), payload.get("avg_kda"))
        win.set_extra_stats(
            payload.get("wins10"),
            payload.get("losses10"),
            payload.get("avg_cs"),
            payload.get("avg_dur"),
            payload.get("best_kda"),
        )
        win.set_top_champs(payload.get("top_champs") or [])

        win.set_status(f"Connected: {platform} • {riot_id}")

        if refresh_thread:
            refresh_thread.quit()

    def _on_refresh_failed(msg: str):
        nonlocal refresh_thread
        win.set_status(msg)
        if refresh_thread:
            refresh_thread.quit()

    win.set_refresh_callback(refresh)

    # Account swap watcher
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

    # ---------- Auto-update on startup ----------
    def start_update_check():
        if not (GITHUB_OWNER and GITHUB_REPO and APP_VERSION):
            return

        t = QThread()
        w = UpdateWorker(GITHUB_OWNER, GITHUB_REPO, APP_VERSION)
        w.moveToThread(t)
        track(t, w)

        w.done.connect(lambda info: dispatcher.run.emit(lambda: _on_update_info(info)), Qt.QueuedConnection)
        w.failed.connect(lambda _err: t.quit(), Qt.QueuedConnection)
        t.started.connect(w.run)
        t.finished.connect(w.deleteLater)
        t.start()

    def _on_update_info(info):
        if not info:
            return

        msg = QMessageBox(win)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Update available")
        msg.setText(f"New version available: {info.latest_version}\n\nUpdate now?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        res = msg.exec()

        if res != QMessageBox.Yes:
            return

        win.set_status("Downloading update…")

        dt = QThread()
        dw = DownloadUpdateWorker(info.asset_url)
        dw.moveToThread(dt)
        track(dt, dw)

        dw.done.connect(lambda path: dispatcher.run.emit(lambda: _on_download_done(path)), Qt.QueuedConnection)
        dw.failed.connect(lambda err: dispatcher.run.emit(lambda: _on_download_failed(err)), Qt.QueuedConnection)
        dt.started.connect(dw.run)
        dt.finished.connect(dw.deleteLater)
        dt.start()

    def _on_download_done(path: Optional[str]):
        if not path:
            QMessageBox.warning(win, "Update failed", "Could not download installer.")
            win.set_status("Update download failed.")
            return
        run_installer(path)
        QApplication.quit()

    def _on_download_failed(err: str):
        QMessageBox.warning(win, "Update failed", err)
        win.set_status("Update failed.")

    QTimer.singleShot(300, start_update_check)
    QTimer.singleShot(150, refresh)

    app.exec()


if __name__ == "__main__":
    main()
