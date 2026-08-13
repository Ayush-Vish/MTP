"""Adapter between SecGuard policy decisions and 5Guard slice requests."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from secguard.policy import ISOLATION_NAMES, IsolationDecision


@dataclass(frozen=True)
class AdaptedRequest:
    """Result of applying one SecGuard decision to a 5Guard request."""

    slice_id: str
    action: str
    original_gamma: int
    target_gamma: int | None
    optimizer_request: Any | None

    @property
    def quarantined(self) -> bool:
        return self.optimizer_request is None

    def to_dict(self) -> dict:
        return {
            "slice_id": self.slice_id,
            "action": self.action,
            "original_gamma": self.original_gamma,
            "original_isolation": ISOLATION_NAMES[self.original_gamma],
            "target_gamma": self.target_gamma,
            "target_isolation": (
                ISOLATION_NAMES[self.target_gamma]
                if self.target_gamma is not None
                else None
            ),
            "sent_to_optimizer": not self.quarantined,
            "request_type": (
                type(self.optimizer_request).__name__
                if self.optimizer_request is not None
                else None
            ),
        }


def adapt_slice_request(request: Any, decision: IsolationDecision) -> AdaptedRequest:
    """Copy a 5Guard request and safely apply the decision to its ``gamma``.

    Quarantined requests are withheld from the optimizer. The input request is
    never mutated, and a decision cannot lower its original SLA isolation.
    """
    if not hasattr(request, "gamma"):
        raise TypeError("5Guard request must expose a numeric 'gamma' attribute")

    original_gamma = request.gamma
    if original_gamma not in ISOLATION_NAMES:
        raise ValueError("5Guard request gamma must be 0, 1, or 2")
    if decision.requested_level != original_gamma:
        raise ValueError(
            "Decision requested_level does not match the request's original gamma"
        )

    if decision.action == "QUARANTINE":
        return AdaptedRequest(
            decision.slice_id,
            decision.action,
            original_gamma,
            None,
            None,
        )

    target_gamma = decision.target_level
    if target_gamma not in ISOLATION_NAMES:
        raise ValueError("Non-quarantine decisions require target level 0, 1, or 2")
    if target_gamma < original_gamma:
        raise ValueError("SecGuard cannot lower the request's SLA isolation")

    optimizer_request = copy.copy(request)
    optimizer_request.gamma = target_gamma
    return AdaptedRequest(
        decision.slice_id,
        decision.action,
        original_gamma,
        target_gamma,
        optimizer_request,
    )

