"""Security metrics for comparing static and risk-adaptive isolation."""

from __future__ import annotations

from dataclasses import dataclass


SHARING_FACTOR = {0: 1.0, 1: 0.5, 2: 0.0}


@dataclass(frozen=True)
class ExposureObservation:
    slice_id: str
    risk_score: float
    impact: float
    isolation_level: int | None


def isolation_exposure(observations: list[ExposureObservation]) -> float:
    """Return a transparent risk/impact/isolation exposure proxy.

    L0 is treated as fully shared, L1 as half exposed, and L2 or quarantine as
    having no cross-slice exposure. This is a proxy, not observed attack spread.
    """
    total = 0.0
    for item in observations:
        if not 0.0 <= item.risk_score <= 1.0:
            raise ValueError("risk_score must be between 0 and 1")
        if item.impact < 0:
            raise ValueError("impact must be non-negative")
        sharing = 0.0 if item.isolation_level is None else SHARING_FACTOR[item.isolation_level]
        total += item.risk_score * item.impact * sharing
    return total


def exposure_reduction(baseline: float, proposed: float) -> float:
    """Return fractional exposure reduction relative to a non-zero baseline."""
    if baseline <= 0:
        raise ValueError("baseline exposure must be positive")
    return (baseline - proposed) / baseline

