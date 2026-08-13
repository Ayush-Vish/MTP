import pytest

from secguard.policy import decide_isolation


def test_low_risk_preserves_requested_isolation() -> None:
    decision = decide_isolation("mc", risk_score=0.01, requested_level=2)
    assert decision.action == "KEEP"
    assert decision.target_level == 2


def test_medium_risk_upgrades_l0_to_l1() -> None:
    decision = decide_isolation("embb", risk_score=0.20, requested_level=0)
    assert decision.action == "UPGRADE_L1"
    assert decision.target_level == 1


def test_high_risk_upgrades_to_l2() -> None:
    decision = decide_isolation("urllc", risk_score=0.50, requested_level=1)
    assert decision.action == "UPGRADE_L2"
    assert decision.target_level == 2


def test_critical_risk_quarantines() -> None:
    decision = decide_isolation("attacker", risk_score=0.90, requested_level=0)
    assert decision.action == "QUARANTINE"
    assert decision.target_level is None


def test_invalid_risk_is_rejected() -> None:
    with pytest.raises(ValueError):
        decide_isolation("bad", risk_score=1.1, requested_level=0)

