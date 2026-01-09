from __future__ import annotations
from typing import List, Optional, Tuple

import requests
from PySide6.QtCore import Qt, QSize, QPoint, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QColor, QPainter, QPen, QBrush, QFontMetrics
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QSpinBox,
    QAbstractSpinBox,
    QSizeGrip,
)

from model import RankedSnapshot, MatchRow


# -----------------------
# Image cache
# -----------------------
_IMAGE_CACHE: dict[str, QPixmap] = {}


def _pixmap_from_url(url: str, size: int) -> QPixmap:
    key = f"{url}|{size}"
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        pix = QPixmap()
        pix.loadFromData(r.content)
        out = pix.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _IMAGE_CACHE[key] = out
        return out
    except Exception:
        return QPixmap()


# -----------------------
# Styling (unchanged content sizes, tighter boxes)
# -----------------------
BASE_FONT = 14
TITLE_FONT = 24
METRIC_FONT = 18
MINITITLE_FONT = 14

DARK_QSS = f"""
QMainWindow, QWidget {{
  background-color: #000000;
  color: #ffffff;
  font-family: Segoe UI;
  font-size: {BASE_FONT}px;
}}

QWidget#WindowFrame {{
  background-color: #000000;
  border: 1px solid #ffffff;
}}

QWidget#TitleBar {{
  background-color: #000000;
  border: 0px;
  border-bottom: 1px solid #ffffff;
}}

QLabel#Subtle {{ color: #d8d8d8; }}

QLabel#Title {{
  font-size: {TITLE_FONT}px;
  font-weight: 700;
}}

QLabel#MiniTitle {{
  font-size: {MINITITLE_FONT}px;
  font-weight: 700;
}}

QLabel#Metric {{
  font-size: {METRIC_FONT}px;
  font-weight: 700;
}}

QPushButton#RefreshBtn {{
  background-color: #000000;
  border: 1px solid #ffffff;
  border-radius: 0px;
  padding: 8px 14px;
}}
QPushButton#RefreshBtn:hover {{ background-color: #101010; }}
QPushButton#RefreshBtn:pressed {{ background-color: #151515; }}

QWidget#Card {{
  background-color: #000000;
  border: 1px solid #ffffff;
  border-radius: 0px;
}}

QSpinBox {{
  background-color: #000000;
  color: #ffffff;
  border: 1px solid #ffffff;
  border-radius: 0px;
  padding: 2px 6px;
}}

QTableWidget {{
  background-color: #000000;
  border: 1px solid #ffffff;
  gridline-color: #222222;
  border-radius: 0px;
}}
QTableWidget::item {{
  border-bottom: 1px solid #111111;
  padding: 2px 6px;
}}
QTableWidget::item:selected {{ background-color: #000000; }}

QHeaderView::section {{
  background-color: #000000;
  color: #ffffff;
  border: 1px solid #ffffff;
  padding: 8px;
}}
"""


# -----------------------
# Animated window button
# -----------------------
class AnimatedWinButton(QPushButton):
    """
    Custom painted button with smooth hover animation.
    """
    def __init__(self, text: str, close_variant: bool = False):
        super().__init__(text)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCheckable(False)

        self._hover = 0.0
        self._pressed = False
        self._close_variant = close_variant

        self.setFixedSize(54, 36)

        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._pressed = True
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def getHoverProgress(self) -> float:
        return self._hover

    def setHoverProgress(self, v: float):
        self._hover = float(v)
        self.update()

    hoverProgress = Property(float, getHoverProgress, setHoverProgress)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        # Colors
        base_bg = QColor(0, 0, 0)
        hover_bg = QColor(16, 16, 16) if not self._close_variant else QColor(34, 0, 0)
        press_bg = QColor(21, 21, 21) if not self._close_variant else QColor(48, 0, 0)

        # Blend background based on hover
        if self._pressed:
            bg = press_bg
        else:
            bg = QColor(
                int(base_bg.red() + (hover_bg.red() - base_bg.red()) * self._hover),
                int(base_bg.green() + (hover_bg.green() - base_bg.green()) * self._hover),
                int(base_bg.blue() + (hover_bg.blue() - base_bg.blue()) * self._hover),
            )

        # Draw background
        p.fillRect(self.rect(), QBrush(bg))

        # Border
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Text
        p.setPen(QColor(255, 255, 255))
        fm = QFontMetrics(self.font())
        text = self.text()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        p.drawText(
            (self.width() - tw) // 2,
            (self.height() + th) // 2 - fm.descent(),
            text
        )
        p.end()


# -----------------------
# Title bar
# -----------------------
class TitleBar(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self._parent = parent
        self._drag_pos: Optional[QPoint] = None

        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        # App title inside topbar (left)
        self.app_title = QLabel("Despectus")
        self.app_title.setObjectName("MiniTitle")

        # Status
        self.status = QLabel("Waiting for League Client…")
        self.status.setObjectName("Subtle")

        # Refresh
        self.refresh_btn = QPushButton("Refresh Now")
        self.refresh_btn.setObjectName("RefreshBtn")

        # Window buttons
        self.btn_min = AnimatedWinButton("—", close_variant=False)
        self.btn_min.clicked.connect(parent.showMinimized)

        self.btn_max = AnimatedWinButton("▢", close_variant=False)
        self.btn_max.clicked.connect(parent.toggle_max_restore)

        self.btn_close = AnimatedWinButton("✕", close_variant=True)
        self.btn_close.clicked.connect(parent.close)

        layout.addWidget(self.app_title, 0, Qt.AlignLeft)
        layout.addSpacing(8)
        layout.addWidget(self.status, 1)
        layout.addWidget(self.refresh_btn)

        layout.addSpacing(10)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            if self._parent.isMaximized():
                self._parent.showNormal()
                self._parent._is_maximized = False
                self._parent._sync_max_button()
                self._drag_pos = e.globalPosition().toPoint()

            delta = e.globalPosition().toPoint() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._parent.toggle_max_restore()
        super().mouseDoubleClickEvent(e)


# -----------------------
# Main Window
# -----------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self._is_maximized = False

        self.window_frame = QWidget()
        self.window_frame.setObjectName("WindowFrame")
        self.setCentralWidget(self.window_frame)

        frame_layout = QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        frame_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        frame_layout.addWidget(self.title_bar)

        root = QWidget()
        frame_layout.addWidget(root, 1)

        # Slightly smaller window (boxes tighter), content sizes unchanged
        self.resize(1220, 800)
        self.setMinimumSize(1120, 740)

        # expose titlebar widgets
        self.status = self.title_bar.status
        self.refresh_btn = self.title_bar.refresh_btn
        self.refresh_btn.clicked.connect(lambda: self.on_manual_refresh())

        # -------------------
        # Cards (reduced padding/spacing ONLY)
        # -------------------

        # Profile
        self.profile_card = QWidget()
        self.profile_card.setObjectName("Card")
        p_outer = QVBoxLayout(self.profile_card)
        p_outer.setContentsMargins(14, 10, 14, 12)  # smaller box padding
        p_outer.setSpacing(8)

        p_title = QLabel("[Profile]")
        p_title.setObjectName("MiniTitle")
        p_outer.addWidget(p_title)

        p_center = QHBoxLayout()
        p_center.setContentsMargins(0, 0, 0, 0)
        p_center.setSpacing(16)

        self.icon = QLabel()
        self.icon.setFixedSize(72, 72)
        self.icon.setAlignment(Qt.AlignCenter)

        self.riot_id = QLabel("—")
        self.riot_id.setObjectName("Title")

        self.level = QLabel("Level: —")
        self.level.setObjectName("Subtle")

        name_box = QVBoxLayout()
        name_box.setSpacing(4)
        name_box.addWidget(self.riot_id)
        name_box.addWidget(self.level)

        p_center.addWidget(self.icon)
        p_center.addLayout(name_box)
        p_center.addStretch(1)

        # keep this centered vertically without extra “empty top” feel
        p_outer.addStretch(1)
        p_outer.addLayout(p_center)
        p_outer.addStretch(1)

        # Rank
        self.ranked_card = QWidget()
        self.ranked_card.setObjectName("Card")
        r_outer = QVBoxLayout(self.ranked_card)
        r_outer.setContentsMargins(14, 10, 14, 12)
        r_outer.setSpacing(8)

        r_title = QLabel("[Rank]")
        r_title.setObjectName("MiniTitle")
        r_outer.addWidget(r_title)

        r_row = QHBoxLayout()
        r_row.setContentsMargins(0, 0, 0, 0)
        r_row.setSpacing(16)

        self.rank_emblem = QLabel()
        self.rank_emblem.setFixedSize(90, 90)
        self.rank_emblem.setAlignment(Qt.AlignCenter)

        r_grid = QGridLayout()
        r_grid.setHorizontalSpacing(26)
        r_grid.setVerticalSpacing(8)

        self.rank_line = QLabel("Rank: —")
        self.rank_line.setObjectName("Title")

        self.lp_line = QLabel("LP: —")
        self.lp_line.setObjectName("Subtle")

        self.wr_line = QLabel("Winrate: —")
        self.wr_line.setObjectName("Subtle")

        self.next_line = QLabel("To next: —")
        self.next_line.setObjectName("Subtle")

        self.est_line = QLabel("Est games: —")
        self.est_line.setObjectName("Subtle")

        self.avg_lp_label = QLabel("Avg LP/W:")
        self.avg_lp_label.setObjectName("Subtle")

        self.avg_lp_spin = QSpinBox()
        self.avg_lp_spin.setRange(1, 60)
        self.avg_lp_spin.setValue(22)
        self.avg_lp_spin.setKeyboardTracking(False)
        self.avg_lp_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.avg_lp_spin.setFixedWidth(44)

        r_grid.addWidget(self.rank_line, 0, 0, 1, 2)
        r_grid.addWidget(self.lp_line, 1, 0)
        r_grid.addWidget(self.wr_line, 1, 1)
        r_grid.addWidget(self.next_line, 2, 0)
        r_grid.addWidget(self.est_line, 2, 1)
        r_grid.addWidget(self.avg_lp_label, 3, 0)
        r_grid.addWidget(self.avg_lp_spin, 3, 1)

        r_row.addWidget(self.rank_emblem)
        r_row.addLayout(r_grid)
        r_row.addStretch(1)

        r_outer.addLayout(r_row)

        # Stats
        self.strip_stats = QWidget()
        self.strip_stats.setObjectName("Card")
        s_outer = QVBoxLayout(self.strip_stats)
        s_outer.setContentsMargins(14, 10, 14, 12)
        s_outer.setSpacing(8)

        s_title = QLabel("[Stats]")
        s_title.setObjectName("MiniTitle")
        s_outer.addWidget(s_title)

        s_grid = QGridLayout()
        s_grid.setHorizontalSpacing(26)
        s_grid.setVerticalSpacing(6)

        self.s_winrate = QLabel("Winrate: —")
        self.s_winrate.setObjectName("Metric")
        self.s_avgkda = QLabel("Avg KDA: —")
        self.s_avgkda.setObjectName("Metric")

        self.s_wl = QLabel("W/L: —")
        self.s_wl.setObjectName("Subtle")
        self.s_avgcs = QLabel("Avg CS: —")
        self.s_avgcs.setObjectName("Subtle")
        self.s_avgdur = QLabel("Avg Dur: —")
        self.s_avgdur.setObjectName("Subtle")
        self.s_bestkda = QLabel("Best KDA: —")
        self.s_bestkda.setObjectName("Subtle")

        s_grid.addWidget(self.s_winrate, 0, 0)
        s_grid.addWidget(self.s_avgkda, 0, 1)
        s_grid.addWidget(self.s_wl, 1, 0)
        s_grid.addWidget(self.s_avgcs, 1, 1)
        s_grid.addWidget(self.s_avgdur, 2, 0)
        s_grid.addWidget(self.s_bestkda, 2, 1)

        s_outer.addLayout(s_grid)

        # Most Played
        self.strip_champs = QWidget()
        self.strip_champs.setObjectName("Card")
        c_outer = QVBoxLayout(self.strip_champs)
        c_outer.setContentsMargins(14, 10, 14, 12)
        c_outer.setSpacing(8)

        c_title = QLabel("[Most Played]")
        c_title.setObjectName("MiniTitle")
        c_outer.addWidget(c_title)

        c_row = QHBoxLayout()
        c_row.setContentsMargins(0, 0, 0, 0)
        c_row.setSpacing(14)

        self.c_sub = QLabel("Top 3 champs")
        self.c_sub.setObjectName("Subtle")
        c_row.addWidget(self.c_sub)
        c_row.addStretch(1)

        # Bigger icons in Most Played
        self.champ_icon_labels = []
        self.champ_count_labels = []
        for _ in range(3):
            col = QVBoxLayout()
            col.setSpacing(4)
            icon = QLabel()
            icon.setFixedSize(56, 56)   # bumped
            icon.setAlignment(Qt.AlignCenter)
            count = QLabel("—")
            count.setAlignment(Qt.AlignCenter)
            count.setObjectName("Subtle")
            col.addWidget(icon)
            col.addWidget(count)
            c_row.addLayout(col)
            self.champ_icon_labels.append(icon)
            self.champ_count_labels.append(count)

        c_outer.addLayout(c_row)

        # Games
        games_title = QLabel("[Games]")
        games_title.setObjectName("MiniTitle")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "W/L", "K/D/A", "CS", "Duration"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        # Bigger champ icons in Games
        self.table.setIconSize(QSize(40, 40))

        # non-interactive feel
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setSelectionMode(QTableWidget.NoSelection)

        # row height to fit larger icon
        self.table.verticalHeader().setDefaultSectionSize(46)

        # -------------------
        # Root layout (reduce empty space between boxes)
        # -------------------
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(6)  # tighter gaps between rows

        top = QHBoxLayout()
        top.setSpacing(6)     # tighter gaps between cards
        top.addWidget(self.profile_card, 2)
        top.addWidget(self.ranked_card, 3)
        layout.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        mid.addWidget(self.strip_stats, 3)
        mid.addWidget(self.strip_champs, 2)
        layout.addLayout(mid)

        layout.addWidget(games_title)
        layout.addWidget(self.table, 1)

        # resize grip
        self._grip = QSizeGrip(self.window_frame)
        self._grip.setFixedSize(18, 18)
        self._grip.raise_()

        self._refresh_callback = None

    # -------------------
    # Window behaviors
    # -------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 2
        self._grip.move(
            self.window_frame.width() - self._grip.width() - margin,
            self.window_frame.height() - self._grip.height() - margin,
        )

    def toggle_max_restore(self):
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
        else:
            self.showMaximized()
            self._is_maximized = True
        self._sync_max_button()

    def _sync_max_button(self):
        self.title_bar.btn_max.setText("❐" if self._is_maximized else "▢")

    def apply_theme(self):
        self.setStyleSheet(DARK_QSS)

    # -------------------
    # Callbacks
    # -------------------
    def set_refresh_callback(self, fn):
        self._refresh_callback = fn

    def set_avg_lp_callback(self, fn):
        self.avg_lp_spin.valueChanged.connect(fn)

    def set_avg_lp(self, value: int):
        self.avg_lp_spin.blockSignals(True)
        self.avg_lp_spin.setValue(int(value))
        self.avg_lp_spin.blockSignals(False)

    def on_manual_refresh(self):
        if self._refresh_callback:
            self._refresh_callback()

    # -------------------
    # UI setters
    # -------------------
    def set_status(self, text: str):
        self.status.setText(text)

    def set_profile(self, display_name: str, riot_id: str, level: int, icon_url: str):
        self.riot_id.setText(riot_id if riot_id and riot_id != "—" else display_name)
        self.level.setText(f"Level: {level}")
        pix = _pixmap_from_url(icon_url, 72)
        if not pix.isNull():
            self.icon.setPixmap(pix)

    def set_rank_emblem(self, emblem_url: str):
        pix = _pixmap_from_url(emblem_url, 90)
        if not pix.isNull():
            self.rank_emblem.setPixmap(pix)

    def clear_rank_emblem(self):
        self.rank_emblem.setPixmap(QPixmap())

    def set_ranked(self, ranked: Optional[RankedSnapshot], next_label: Optional[str], est_games: Optional[int]):
        if not ranked:
            self.rank_line.setText("Rank: Unranked (Solo/Duo)")
            self.lp_line.setText("LP: —")
            self.wr_line.setText("Winrate: —")
            self.next_line.setText("To next: —")
            self.est_line.setText("Est games: —")
            return

        self.rank_line.setText(f"Rank: {ranked.tier.title()} {ranked.rank} (Solo/Duo)")
        self.lp_line.setText(f"LP: {ranked.lp}")
        self.wr_line.setText(f"Winrate: {ranked.winrate:.1f}% ({ranked.wins}W/{ranked.losses}L)")
        self.next_line.setText(f"To next: {next_label}" if next_label else "To next: —")
        self.est_line.setText(f"Est games: {est_games}" if est_games is not None else "Est games: —")

    def set_recent_stats(self, winrate: Optional[float], avg_kda: Optional[float]):
        if winrate is None or avg_kda is None:
            self.s_winrate.setText("Winrate: —")
            self.s_avgkda.setText("Avg KDA: —")
            return
        self.s_winrate.setText(f"Winrate: {winrate:.0f}%")
        self.s_avgkda.setText(f"Avg KDA: {avg_kda:.2f}")

    def set_extra_stats(
        self,
        wins10: Optional[int],
        losses10: Optional[int],
        avg_cs: Optional[float],
        avg_dur: Optional[float],
        best_kda: Optional[float],
    ):
        self.s_wl.setText(f"W/L: {wins10}/{losses10}" if wins10 is not None else "W/L: —")
        self.s_avgcs.setText(f"Avg CS: {avg_cs:.0f}" if avg_cs is not None else "Avg CS: —")
        self.s_avgdur.setText(f"Avg Dur: {avg_dur:.0f}m" if avg_dur is not None else "Avg Dur: —")
        self.s_bestkda.setText(f"Best KDA: {best_kda:.2f}" if best_kda is not None else "Best KDA: —")

    def set_top_champs(self, champs: List[Tuple[str, str, int]]):
        for i in range(3):
            icon_lbl = self.champ_icon_labels[i]
            cnt_lbl = self.champ_count_labels[i]
            if i < len(champs):
                _, icon_url, count = champs[i]
                pix = _pixmap_from_url(icon_url, 56) if icon_url else QPixmap()
                icon_lbl.setPixmap(pix if not pix.isNull() else QPixmap())
                cnt_lbl.setText(f"x{count}")
            else:
                icon_lbl.setPixmap(QPixmap())
                cnt_lbl.setText("—")

    def set_matches(self, rows: List[MatchRow]):
        self.table.setRowCount(0)

        loss_red = QColor(120, 10, 10)
        golden = QColor(184, 154, 24)

        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            icon_widget = QLabel()
            icon_widget.setFixedSize(40, 40)
            icon_widget.setAlignment(Qt.AlignCenter)
            if row.champ_icon_url:
                pix = _pixmap_from_url(row.champ_icon_url, 40)
                if not pix.isNull():
                    icon_widget.setPixmap(pix)
            self.table.setCellWidget(r, 0, icon_widget)

            wl_text = "WIN" if row.win else "LOSS"
            wl_item = QTableWidgetItem(wl_text)
            f = wl_item.font()
            f.setBold(True)
            wl_item.setFont(f)
            wl_item.setTextAlignment(Qt.AlignCenter)
            wl_item.setForeground(Qt.white if row.win else loss_red)
            self.table.setItem(r, 1, wl_item)

            kda_item = QTableWidgetItem(row.kda_str)
            kda_item.setTextAlignment(Qt.AlignCenter)
            kda_ratio = (row.k + row.a) / max(1, row.d)
            if kda_ratio >= 8.0:
                kda_item.setForeground(golden)
            self.table.setItem(r, 2, kda_item)

            cs_item = QTableWidgetItem(str(row.cs))
            cs_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, cs_item)

            dur_item = QTableWidgetItem(f"{row.duration_min}m")
            dur_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 4, dur_item)
