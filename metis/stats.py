"""Small-n aware summary statistics. No scipy dependency: t multipliers for
95% CIs come from a lookup table, falling back to the normal 1.96 for df > 30."""

import math

_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def ci95(xs) -> float:
    """Half-width of the 95% confidence interval around the mean."""
    n = len(xs)
    if n < 2:
        return 0.0
    t = _T95.get(n - 1, 1.96)
    return t * stdev(xs) / math.sqrt(n)


def fmt_mean_ci(xs, digits=2) -> str:
    if not xs:
        return "-"
    return f"{mean(xs):.{digits}f} ± {ci95(xs):.{digits}f}"
