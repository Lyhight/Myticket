import pytest

from app.evals.statistics import wilson_interval


def test_wilson_interval_exposes_small_sample_uncertainty() -> None:
    lower, upper = wilson_interval(20, 20)

    assert lower == pytest.approx(0.83887, rel=1e-4)
    assert upper == 1.0


def test_wilson_interval_handles_empty_sample() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)
