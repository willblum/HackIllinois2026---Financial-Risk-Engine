from pydantic import BaseModel, Field
from typing import Optional
import uuid
import time


class TimeSeriesPoint(BaseModel):
    timestamp: float  # unix epoch
    value: float


class NarrativeDirection(BaseModel):
    """
    A persistent semantic category stored in ChromaDB.
    Represents a real-world narrative (e.g. "energy supply shock",
    "regional banking stress") discovered from news flow.

    Individual news stories are NOT stored here. A story either
    updates an existing narrative's metrics or triggers creation
    of a new narrative if it doesn't fit any existing one.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str                        # LLM-generated short label
    description: str                 # LLM-generated summary of the narrative direction
    created_at: float = Field(default_factory=time.time)
    last_updated: float = Field(default_factory=time.time)
    event_count: int = 0             # number of news stories that have updated this narrative

    # Time series stored as lists of points (serialized to JSON in Chroma metadata)
    surprise_series: list[TimeSeriesPoint] = []
    impact_series: list[TimeSeriesPoint] = []

    # Rolling context: last N headlines that contributed to this narrative
    recent_headlines: list[str] = []

    @property
    def current_surprise(self) -> Optional[float]:
        """Exponential moving average (α=0.35) over the last 50 data points.
        Recent events dominate but old spikes decay slowly, giving a smoother
        and more representative signal than the last-value-only approach."""
        if not self.surprise_series:
            return None
        recent = self.surprise_series[-50:]
        alpha = 0.35
        ema = recent[0].value
        for pt in recent[1:]:
            ema = alpha * pt.value + (1 - alpha) * ema
        return round(ema, 4)

    @property
    def current_impact(self) -> Optional[float]:
        """Exponential moving average (α=0.35) over the last 50 data points."""
        if not self.impact_series:
            return None
        recent = self.impact_series[-50:]
        alpha = 0.35
        ema = recent[0].value
        for pt in recent[1:]:
            ema = alpha * pt.value + (1 - alpha) * ema
        return round(ema, 4)

    @property
    def model_risk(self) -> Optional[float]:
        """Composite risk score spread across [0, 1].

        Blends the EMA-based base risk with the peak risk seen in the last
        10 events (35 % weight).  This means a narrative that once had a
        severe shock still carries elevated risk even after calmer updates,
        while a consistently low-signal narrative stays near the bottom.
        """
        s = self.current_surprise
        i = self.current_impact
        if s is None or i is None:
            return None

        base = (s * i) ** 0.5  # geometric mean of EMA values

        # Peak factor: blend in the worst recent window so single spikes matter
        if len(self.surprise_series) >= 2 and len(self.impact_series) >= 2:
            tail_s = [p.value for p in self.surprise_series[-10:]]
            tail_i = [p.value for p in self.impact_series[-10:]]
            peak = (max(tail_s) * max(tail_i)) ** 0.5
            risk = 0.65 * base + 0.35 * peak
        else:
            risk = base

        return round(min(1.0, risk), 4)

    def append_surprise(self, value: float, timestamp: float = None):
        self.surprise_series.append(
            TimeSeriesPoint(timestamp=timestamp or time.time(), value=value)
        )
        self.last_updated = time.time()

    def append_impact(self, value: float, timestamp: float = None):
        self.impact_series.append(
            TimeSeriesPoint(timestamp=timestamp or time.time(), value=value)
        )
        self.last_updated = time.time()

    def add_headline(self, headline: str, max_recent: int = 10):
        self.recent_headlines.append(headline)
        self.recent_headlines = self.recent_headlines[-max_recent:]
        self.event_count += 1
        self.last_updated = time.time()
