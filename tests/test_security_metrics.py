import pytest

from secguard.security_metrics import (
    ExposureObservation,
    exposure_reduction,
    isolation_exposure,
)


def test_exposure_decreases_as_isolation_increases() -> None:
    l0 = isolation_exposure([ExposureObservation("s", 0.8, 2.0, 0)])
    l1 = isolation_exposure([ExposureObservation("s", 0.8, 2.0, 1)])
    l2 = isolation_exposure([ExposureObservation("s", 0.8, 2.0, 2)])
    quarantine = isolation_exposure([ExposureObservation("s", 0.8, 2.0, None)])

    assert l0 == pytest.approx(1.6)
    assert l1 == pytest.approx(0.8)
    assert l2 == 0
    assert quarantine == 0


def test_exposure_reduction() -> None:
    assert exposure_reduction(0.8, 0.2) == pytest.approx(0.75)


def test_invalid_observation_is_rejected() -> None:
    with pytest.raises(ValueError):
        isolation_exposure([ExposureObservation("s", 1.1, 1.0, 0)])

