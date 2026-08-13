"""Translate a slice attack-risk score into a 5Guard isolation action."""

from dataclasses import asdict, dataclass


ISOLATION_NAMES = {0: "L0", 1: "L1", 2: "L2"}


@dataclass(frozen=True)
class IsolationDecision:
    slice_id: str
    requested_level: int
    risk_score: float
    action: str
    target_level: int | None
    reason: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["requested_isolation"] = ISOLATION_NAMES[self.requested_level]
        result["target_isolation"] = (
            ISOLATION_NAMES[self.target_level]
            if self.target_level is not None
            else None
        )
        return result


def decide_isolation(
    slice_id: str,
    risk_score: float,
    requested_level: int,
    l1_threshold: float = 0.15,
    l2_threshold: float = 0.40,
    quarantine_threshold: float = 0.75,
) -> IsolationDecision:
    """Return a security action while never weakening the requested SLA level."""
    if requested_level not in ISOLATION_NAMES:
        raise ValueError("requested_level must be 0, 1, or 2")
    if not 0.0 <= risk_score <= 1.0:
        raise ValueError("risk_score must be between 0 and 1")
    if not 0 <= l1_threshold < l2_threshold < quarantine_threshold <= 1:
        raise ValueError("thresholds must be strictly increasing within [0, 1]")

    if risk_score >= quarantine_threshold:
        return IsolationDecision(
            slice_id,
            requested_level,
            risk_score,
            "QUARANTINE",
            None,
            "Critical attack likelihood; remove the slice from shared resources.",
        )

    risk_floor = 2 if risk_score >= l2_threshold else 1 if risk_score >= l1_threshold else 0
    target = max(requested_level, risk_floor)
    action = "KEEP" if target == requested_level else f"UPGRADE_{ISOLATION_NAMES[target]}"
    reason = (
        "Risk is within the accepted range; preserve the SLA isolation level."
        if action == "KEEP"
        else f"Risk requires at least {ISOLATION_NAMES[target]} isolation."
    )
    return IsolationDecision(slice_id, requested_level, risk_score, action, target, reason)

