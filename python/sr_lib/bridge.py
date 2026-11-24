"""Share bridge, Python mirror of APP.V_BRIDGE_ALL (L6, SR-022).

Used only by tests: it checks the SQL row by row (T-BR-02) and pins the method with hand-computed cases
(T-BR-03..05). The pipeline never computes the bridge in Python (AGENTS.md rule 8).

share = distribution share x velocity index x price index x promo index, each relative to the category.
Each term in points is 100 x L(s1, s0) x ln(F1 / F0), where L is the logarithmic mean, so the terms add up
exactly to the share change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_MODES = "ABCD"


@dataclass(frozen=True)
class PeriodInputs:
    s: float; cs: float | None                     # brand and category value sales
    tdp: float | None; ctdp: float | None          # brand and category TDP (sum of item %ACV)
    u: float | None; cu: float | None              # units
    b: float | None; cb: float | None              # base (non-promoted) value
    bu: float | None; cbu: float | None            # base units


@dataclass(frozen=True)
class BridgeResult:
    mode: str; status: str; d_share_pts: float
    dist_pts: float | None; velocity_pts: float | None
    price_pts: float | None; promo_pts: float | None
    residual_pts: float | None     # None when no terms were computed (mode D, or status not OK): see B03


def log_mean(a: float, b: float) -> float:
    """L(a, b) = (a - b) / (ln a - ln b), with L(a, a) = a. Matches the SQL guard ABS(a - b) < 1e-12."""
    if abs(a - b) < 1e-12:
        return a
    return (a - b) / (math.log(a) - math.log(b))


def _pos(*xs: float | None) -> bool:
    """SQL LEAST(...) > 0: NULL anywhere makes it false."""
    return all(x is not None and x > 0 for x in xs)


def pick_mode(cur: PeriodInputs, base: PeriodInputs, cap_mode: str) -> str:
    """Best mode the row supports, capped by OPS.CAPABILITY.MAX_BRIDGE_MODE."""
    cap = _MODES.index(cap_mode)
    tdp = (cur.tdp, base.tdp, cur.ctdp, base.ctdp)
    if cap <= 0 and _pos(*tdp, cur.bu, base.bu, cur.cbu, base.cbu, cur.b, base.b, cur.cb, base.cb):
        return "A"
    if cap <= 1 and _pos(*tdp, cur.u, base.u, cur.cu, base.cu):
        return "B"
    if cap <= 2 and _pos(*tdp):
        return "C"
    return "D"


def status_of(cur: PeriodInputs, base: PeriodInputs) -> str:
    if not _pos(cur.cs, base.cs):
        return "NO_DATA"
    if base.s <= 0 and cur.s > 0:
        return "NEW"
    if cur.s <= 0 and base.s > 0:
        return "EXIT"
    if cur.s <= 0 and base.s <= 0:
        return "NO_DATA"
    return "OK"


def _indices(p: PeriodInputs, mode: str) -> tuple[float | None, float | None, float | None, float | None]:
    """(distribution share, velocity index, price index, promo index) for one period."""
    ds = p.tdp / p.ctdp if mode != "D" else None
    if mode == "A":
        v = (p.bu / p.tdp) / (p.cbu / p.ctdp)
        pi = (p.b / p.bu) / (p.cb / p.cbu)
        pri = (p.s / p.b) / (p.cs / p.cb)
    elif mode == "B":
        v = (p.u / p.tdp) / (p.cu / p.ctdp)
        pi = (p.s / p.u) / (p.cs / p.cu)
        pri = None
    elif mode == "C":
        v = (p.s / p.tdp) / (p.cs / p.ctdp)
        pi = pri = None
    else:
        v = pi = pri = None
    return ds, v, pi, pri


def bridge(cur: PeriodInputs, base: PeriodInputs, cap_mode: str = "A") -> BridgeResult:
    mode = pick_mode(cur, base, cap_mode)
    status = status_of(cur, base)
    if not _pos(cur.cs, base.cs):
        return BridgeResult(mode, status, math.nan, None, None, None, None, None)
    s1, s0 = cur.s / cur.cs, base.s / base.cs
    d_pts = 100.0 * (s1 - s0)
    if status != "OK" or mode == "D":
        return BridgeResult(mode, status, d_pts, None, None, None, None, None)
    weight = log_mean(s1, s0)
    f1, f0 = _indices(cur, mode), _indices(base, mode)
    terms = [100.0 * weight * math.log(a / b) if a is not None and b is not None else None for a, b in zip(f1, f0)]
    residual = d_pts - sum(t for t in terms if t is not None)
    return BridgeResult(mode, status, d_pts, terms[0], terms[1], terms[2], terms[3], residual)
