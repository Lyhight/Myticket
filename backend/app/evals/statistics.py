import math


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    """Return a 95% Wilson score interval for a binomial proportion."""
    if total <= 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = proportion + z**2 / (2 * total)
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z**2 / (4 * total**2)
    )
    lower = max(0.0, (centre - margin) / denominator)
    upper = min(1.0, (centre + margin) / denominator)
    if successes == 0:
        lower = 0.0
    if successes == total:
        upper = 1.0
    return (lower, upper)
