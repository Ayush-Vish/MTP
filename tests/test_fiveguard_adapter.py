from dataclasses import dataclass

import pytest

from secguard.fiveguard_adapter import adapt_slice_request
from secguard.policy import decide_isolation


@dataclass
class StubSliceRequest:
    gamma: int
    R: float = 100.0
    timeout: float = 5.0


@pytest.mark.parametrize(
    ("risk", "gamma", "expected_gamma"),
    [(0.01, 0, 0), (0.20, 0, 1), (0.50, 1, 2), (0.01, 2, 2)],
)
def test_adapter_outputs_valid_5guard_gamma(
    risk: float, gamma: int, expected_gamma: int
) -> None:
    request = StubSliceRequest(gamma=gamma)
    decision = decide_isolation("slice", risk, gamma)

    result = adapt_slice_request(request, decision)

    assert result.optimizer_request.gamma == expected_gamma
    assert request.gamma == gamma
    assert result.optimizer_request.R == request.R
    assert result.optimizer_request.timeout == request.timeout


def test_quarantine_is_not_sent_to_optimizer() -> None:
    request = StubSliceRequest(gamma=2)
    decision = decide_isolation("slice", 0.90, 2)

    result = adapt_slice_request(request, decision)

    assert result.quarantined
    assert result.optimizer_request is None


def test_adapter_rejects_decision_for_another_sla() -> None:
    request = StubSliceRequest(gamma=1)
    mismatched = decide_isolation("slice", 0.01, 0)

    with pytest.raises(ValueError, match="does not match"):
        adapt_slice_request(request, mismatched)

