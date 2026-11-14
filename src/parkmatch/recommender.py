"""Rule-based trail filtering and explainable scoring (PRD section 6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from parkmatch.catalog import DIFFICULTY_LEVELS


# Upper bound in hours for each time choice; None means no upper bound.
TIME_BUCKETS: dict[str, tuple[float, float | None]] = {
    "up_to_2": (0.0, 2.0),
    "2_to_4": (2.0, 4.0),
    "over_4": (4.0, None),
}
TIME_LABELS = {
    "up_to_2": "Up to 2 hours",
    "2_to_4": "2–4 hours",
    "over_4": "More than 4 hours",
}
SCENERY_LABELS = {
    "mountain_views": "Mountain views",
    "waterfalls": "Waterfalls",
    "lakes": "Lakes",
    "forests": "Forests",
    "wildflowers": "Wildflowers",
}

# Illustrative, unvalidated starting weights from the PRD.
DEFAULT_WEIGHTS = {"scenery": 0.40, "difficulty": 0.35, "time": 0.25}


@dataclass(frozen=True)
class Preferences:
    max_difficulty: str  # hardest level the user accepts
    time_bucket: str  # key of TIME_BUCKETS
    scenery: tuple[str, ...] = ()


@dataclass
class Recommendation:
    trail_id: str
    score: float
    components: dict[str, float]
    reasons: list[str]


@dataclass
class RecommendationResult:
    recommendations: list[Recommendation]
    excluded: dict[str, str] = field(default_factory=dict)  # trail_id -> reason


def _bucket_index(hours: float) -> int:
    """0 for up to 2 hours, 1 for up to 4, 2 for longer."""
    if hours <= 2.0:
        return 0
    if hours <= 4.0:
        return 1
    return 2


def _format_hours(hours: float) -> str:
    return f"{hours:g} hour" + ("" if hours == 1 else "s")


def recommend(
    trails: Sequence[dict[str, Any]],
    preferences: Preferences,
    weights: dict[str, float] | None = None,
    top_n: int = 3,
) -> RecommendationResult:
    """Filter out unsuitable trails, score the rest, return the best ``top_n``.

    A trail with an unknown difficulty or duration is excluded, not assumed
    to fit. With no scenery interests chosen, scenery is left out of the
    score and the other weights are rescaled.
    """
    weights = dict(weights or DEFAULT_WEIGHTS)
    if not preferences.scenery:
        weights.pop("scenery", None)
    total_weight = sum(weights.values())

    max_level = DIFFICULTY_LEVELS.index(preferences.max_difficulty)
    wanted_bucket = list(TIME_BUCKETS).index(preferences.time_bucket)
    time_limit = TIME_BUCKETS[preferences.time_bucket][1]

    result = RecommendationResult(recommendations=[])
    for trail in trails:
        trail_id = trail["trail_id"]
        difficulty = trail.get("difficulty")
        hours = trail.get("estimated_hours")

        if difficulty is None:
            result.excluded[trail_id] = "Difficulty is unknown."
            continue
        if hours is None:
            result.excluded[trail_id] = "Hiking time is unknown."
            continue
        level = DIFFICULTY_LEVELS.index(difficulty)
        if level > max_level:
            result.excluded[trail_id] = (
                f"Rated {difficulty}, above your {preferences.max_difficulty} limit."
            )
            continue
        if time_limit is not None and hours > time_limit:
            result.excluded[trail_id] = (
                f"Takes about {_format_hours(hours)}, longer than your time."
            )
            continue

        components: dict[str, float] = {}
        reasons: list[str] = []

        if preferences.scenery:
            matched = [tag for tag in preferences.scenery if tag in trail["scenery_tags"]]
            components["scenery"] = len(matched) / len(preferences.scenery)
            if matched:
                names = ", ".join(SCENERY_LABELS[tag].lower() for tag in matched)
                reasons.append(
                    f"Has {len(matched)} of your {len(preferences.scenery)} "
                    f"scenery picks: {names}."
                )
            else:
                reasons.append("Has none of your scenery picks.")

        gap = max_level - level
        components["difficulty"] = (1.0, 0.5, 0.0)[gap]
        if gap == 0:
            reasons.append(f"Rated {difficulty}, the level you chose.")
        else:
            reasons.append(
                f"Rated {difficulty}, easier than your {preferences.max_difficulty} limit."
            )

        shortfall = wanted_bucket - _bucket_index(hours)
        components["time"] = (1.0, 0.5, 0.25)[max(shortfall, 0)]
        if shortfall <= 0:
            reasons.append(f"About {_format_hours(hours)}, which fits your time.")
        else:
            reasons.append(
                f"About {_format_hours(hours)}, shorter than the time you have."
            )

        score = sum(weights[name] * components[name] for name in weights) / total_weight
        result.recommendations.append(
            Recommendation(trail_id, round(score, 4), components, reasons)
        )

    result.recommendations.sort(key=lambda rec: (-rec.score, rec.trail_id))
    result.recommendations = result.recommendations[:top_n]
    return result
