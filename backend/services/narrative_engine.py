"""
Narrative Routing Engine
========================
Decides whether an incoming story updates an existing narrative direction
or spawns a new one, then persists the result to ChromaDB.

Two entry points:

    ingest_story(headline, body)
        All-in-one: embeds the story itself, then routes. Use for single
        manual ingests where you don't need batch efficiency.

    route_with_embedding(headline, body, embedding)
        Routing only — embedding is supplied externally. Use this when
        the caller has already batch-embedded a set of stories via
        embed_batch() for efficiency (the /api/pipeline/process flow).

Routing rule (cosine distance in [0, 2]):
    distance < NEW_NARRATIVE_THRESHOLD  → update existing narrative
    distance >= NEW_NARRATIVE_THRESHOLD → create new narrative direction
"""

import time
import threading
from core.config import settings
from db import vector_store
from models.narrative import NarrativeDirection
from services.embedder import embed_text
from services.llm_client import label_narrative  # score_story replaced by heuristic

NEW_NARRATIVE_THRESHOLD: float = settings.new_narrative_threshold

# Prevents two threads from simultaneously deciding to create the same narrative
_route_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Fast heuristic scorer — replaces Cerebras score_story() calls
# ---------------------------------------------------------------------------

_HIGH_IMPACT: frozenset[str] = frozenset([
    "collapse", "default", "bankrupt", "crisis", "crash", "recession",
    "shutdown", "sanctions", "war", "emergency", "contagion", "bank run",
    "rate hike", "rate cut", "systemic", "panic", "invasion", "devaluation",
    "insolvency", "failure", "downgrade", "freeze", "seized", "bailout",
    "hyperinflation", "debt ceiling", "sovereign default", "credit crisis",
])

_MED_IMPACT: frozenset[str] = frozenset([
    "inflation", "tariff", "regulation", "earnings", "gdp", "unemployment",
    "deficit", "debt", "risk", "concern", "warning", "fell", "surge",
    "decline", "rally", "threat", "pressure", "layoff", "volatility",
    "correction", "tightening", "slowdown", "contraction", "revision",
    "disruption", "shortage", "interest rate", "yield", "spread",
])


def _heuristic_score(headline: str, body: str, distance: float) -> dict:
    """
    Zero-latency scorer producing well-spread values across [0, 1].

    Surprise — two-segment scale so both updates and creates fill their
    natural ranges instead of all cramming against 1.0:

      Updates (distance < threshold): mapped to [0.02, 0.65]
        A story very close to the narrative centroid is routine (low surprise).
        A story right at the edge of the cluster is genuinely surprising (0.65).

      Creates (distance >= threshold): mapped to [0.65, 1.0]
        The further a story sits from every existing narrative, the more novel
        it is.  inf distance (empty DB, first story) is capped at ~0.94.

    Impact — keyword count with diminishing returns and a near-zero floor.
    Range: ~0.04 (no signal words) → 1.0 (multiple high-severity hits).
    """
    T = NEW_NARRATIVE_THRESHOLD

    if distance < T:
        # Update segment: [0, T] → [0.02, 0.65]
        raw = distance / max(T, 0.01)           # 0 → 0, approach-threshold → 1
        surprise = round(max(0.02, 0.65 * (raw ** 0.65)), 3)
    else:
        # Create segment: [T, 2.0] → [0.65, 1.0]
        effective = min(distance, 2.0) if distance < float("inf") else 1.5
        raw = (effective - T) / max(2.0 - T, 0.01)   # 0 at threshold, 1 at max
        surprise = round(min(1.0, 0.65 + 0.35 * (raw ** 0.5)), 3)

    text = (headline + " " + body[:600]).lower()
    high_hits = sum(1 for kw in _HIGH_IMPACT if kw in text)
    med_hits  = sum(1 for kw in _MED_IMPACT  if kw in text)

    impact_from_high = min(0.75, high_hits * 0.30)
    impact_from_med  = min(0.25, med_hits  * 0.04)
    impact = round(max(0.04, impact_from_high + impact_from_med), 3)

    return {"surprise": surprise, "impact": impact}


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def ingest_story(headline: str, body: str) -> dict:
    """
    Embed the story, then route it. Convenience wrapper for single-story use.
    Calls embed_text() → Modal Embedder (one network call per story).
    For bulk processing, use route_with_embedding() with pre-computed embeddings.
    """
    full_text = f"{headline}\n\n{body}"
    embedding = embed_text(full_text)
    return route_with_embedding(headline, body, embedding)


def route_with_embedding(headline: str, body: str, embedding: list[float]) -> dict:
    """
    Route a story using a pre-computed embedding vector.

    This is the core routing function. The embedding must be a 384-dim
    L2-normalized float list produced by the Modal Embedder.

    Called by:
        - ingest_story()               (single-story path)
        - /api/pipeline/process        (batch path — embedding pre-computed upstream)
    """
    full_text = f"{headline}\n\n{body}"

    with _route_lock:
        nearest = vector_store.query_nearest(embedding, n_results=5)
        best_narrative, best_distance = (
            (nearest[0][0], nearest[0][1]) if nearest else (None, float("inf"))
        )
        route_to_existing = (
            best_narrative is not None and best_distance < NEW_NARRATIVE_THRESHOLD
        )

    if route_to_existing:
        action = "updated"
        narrative = _update_narrative(best_narrative, embedding, headline, full_text, best_distance)
    else:
        action = "created"
        narrative = _create_narrative(embedding, headline, full_text, best_distance)

    return {
        "action": action,
        "narrative_id": narrative.id,
        "narrative_name": narrative.name,
        "best_distance": round(best_distance, 4) if best_narrative else None,
        "threshold": NEW_NARRATIVE_THRESHOLD,
        "current_surprise": narrative.current_surprise,
        "current_impact": narrative.current_impact,
        "model_risk": narrative.model_risk,
        "narrative_event_count": narrative.event_count,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_narrative(
    narrative: NarrativeDirection,
    story_embedding: list[float],
    headline: str,
    full_text: str,
    distance: float = 0.2,
) -> NarrativeDirection:
    # Heuristic scorer — instant, no network call
    scores = _heuristic_score(headline, full_text, distance)

    now = time.time()
    # Capture event_count BEFORE add_headline increments it (needed for blend)
    n_before = narrative.event_count

    narrative.append_surprise(scores["surprise"], timestamp=now)
    narrative.append_impact(scores["impact"], timestamp=now)
    narrative.add_headline(headline)

    current_embedding = vector_store.get_embedding(narrative.id)
    updated_embedding = _blend_embedding(current_embedding, story_embedding, n=n_before)

    vector_store.update_narrative(narrative, new_embedding=updated_embedding)
    return narrative


def _create_narrative(
    story_embedding: list[float],
    headline: str,
    full_text: str,
    distance: float = float("inf"),
) -> NarrativeDirection:
    label = label_narrative(full_text)
    scores = _heuristic_score(headline, full_text, distance)

    now = time.time()
    narrative = NarrativeDirection(
        name=label["name"],
        description=label["description"],
        created_at=now,
        last_updated=now,
    )
    narrative.append_surprise(scores["surprise"], timestamp=now)
    narrative.append_impact(scores["impact"], timestamp=now)
    narrative.add_headline(headline)

    vector_store.add_narrative(narrative, embedding=story_embedding)
    return narrative


def _blend_embedding(
    current: list[float],
    new: list[float],
    n: int,
) -> list[float]:
    """
    Online mean update: new_centroid = old * (n/(n+1)) + story * (1/(n+1))
    n must be the event_count BEFORE the new story was added.
    Re-normalizes to unit length after blending.
    """
    if n <= 0:
        return new
    w_old = n / (n + 1)
    w_new = 1.0 / (n + 1)
    blended = [c * w_old + v * w_new for c, v in zip(current, new)]
    mag = sum(x ** 2 for x in blended) ** 0.5
    return [x / mag for x in blended] if mag > 0 else blended
