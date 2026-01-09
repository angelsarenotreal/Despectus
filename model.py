from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class RankedSnapshot:
    queue: str
    tier: str
    rank: str
    lp: int
    wins: int
    losses: int

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def winrate(self) -> float:
        g = self.games
        return (self.wins / g) * 100.0 if g else 0.0

@dataclass
class MatchRow:
    match_id: str
    win: bool
    champion_name: str
    champ_icon_url: str
    k: int
    d: int
    a: int
    cs: int
    vision: int
    duration_min: int

    @property
    def kda_str(self) -> str:
        return f"{self.k}/{self.d}/{self.a}"
