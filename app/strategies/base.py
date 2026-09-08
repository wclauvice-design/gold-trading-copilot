"""Structures de donnees communes a toutes les strategies."""
from dataclasses import dataclass, field
from typing import Literal, Optional

Direction = Literal["long", "short", "wait"]


@dataclass
class StrategySignal:
    name: str
    direction: Direction
    confidence: float  # 0-100
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rationale: str = ""
    details: dict = field(default_factory=dict)

    def risk_reward(self) -> Optional[float]:
        if self.entry is None or self.stop_loss is None or self.take_profit is None:
            return None
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit - self.entry)
        if risk == 0:
            return None
        return round(reward / risk, 2)
