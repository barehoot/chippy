"""Synthetic NIQ-shaped data for the local SQL harness (deterministic).

110 weeks to 2026-11-07; a parent market M0 ("All India") whose rows are the sum of four child retailers plus
unlisted trade; the scope category "Biscuits" (eight brands, private label included) and an out-of-scope
category; and five planted events in the last four weeks, each one something Share Radar must find:

  E1  Crunchy (focus manufacturer) loses distribution at MegaMart       -> a ranked loss, distribution-led
  E2  Golden Bake gains distribution at QuickShop                       -> a ranked gain
  E3  FreshCo's feed stops                                              -> R2_FEED on M0, R6_GAP on FreshCo
  E4  Butter Joy's items are recoded at Store 24                        -> R4_RECODE (if its shift is gated)
  E5  a one-week category spike at Store 24                             -> R5_SPIKE
  E6  Choco Bites loses distribution at MegaMart in the latest week only  -> early warning DIST_DROP
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

AS_OF = date(2026, 11, 7)
N_WEEKS = 110
WEEKS = [AS_OF - timedelta(weeks=i) for i in range(N_WEEKS - 1, -1, -1)]
LAST4 = set(WEEKS[-4:])
CATEGORY = "Biscuits"
PARENT = "M0"

MARKETS = [  # MARKET_ID, MARKET_NAME, MARKET_LEVEL, PARENT_MARKET_ID, RETAILER, CHANNEL, REGION, size
    ("M0", "All India", "TOTAL", None, None, None, None, 0),
    ("M1", "MegaMart", "RETAILER", "M0", "MegaMart", "Modern trade", "North", 1.0),
    ("M2", "QuickShop", "RETAILER", "M0", "QuickShop", "Modern trade", "South", 0.7),
    ("M3", "Store 24", "RETAILER", "M0", "Store 24", "Convenience", "West", 0.5),
    ("M4", "FreshCo", "RETAILER", "M0", "FreshCo", "Modern trade", "East", 0.4),
]
REST_SIZE = 0.6          # unlisted trade, in the parent only

BRANDS = [  # brand, manufacturer, private label, items, base weekly units per ACV point, price
    ("Crunchy", "Acme Foods", False, 3, 9.0, 42.0),
    ("Choco Bites", "Acme Foods", False, 3, 6.0, 55.0),
    ("Golden Bake", "Rival Co", False, 3, 7.0, 40.0),
    ("Butter Joy", "Rival Co", False, 3, 5.0, 48.0),
    ("Tea Time", "Tea Co", False, 3, 5.5, 35.0),
    ("Nutri Max", "Health Co", False, 2, 3.0, 70.0),
    ("Bake 7", "Small Co", False, 2, 2.5, 30.0),
    ("Store Brand", "Private Label", True, 2, 4.0, 25.0),
]
OTHER = [("Leaf Gold", "Tea Co", False, 2, 6.0, 90.0)]           # out-of-scope category "Tea"


def _h(text: str) -> int:
    """Stable across processes (str.__hash__ is randomised per process)."""
    return sum(map(ord, text))


def products() -> list[tuple]:
    out = []
    for cat, brands in ((CATEGORY, BRANDS), ("Tea", OTHER)):
        for brand, maker, pl, n, *_ in brands:
            for i in range(1, n + 1):
                out.append((f"{brand[:3].upper()}-{i}", f"{brand} {i}", brand, maker, cat,
                            "Cookies" if i % 2 else "Crackers", f"{100 * (i + 1)}g", pl))
    out.append(("BUT-9", "Butter Joy 1 new code", "Butter Joy", "Rival Co", CATEGORY, "Cookies", "200g", False))  # E4
    return out


def facts() -> list[tuple]:
    """(WEEK_END_DATE, MARKET_ID, PRODUCT_ID, VALUE_SALES, VOLUME_SALES, UNIT_SALES, ACV_DIST_PCT,
        BASE_VALUE_SALES, BASE_UNIT_SALES, STORES_SELLING, DATA_VERSION)"""
    rng = random.Random(2026)
    prods = {p[0]: p for p in products()}
    params = {b[0]: b for b in BRANDS + OTHER}
    acv0 = {(m[0], pid): rng.uniform(40, 90) for m in MARKETS[1:] for pid in prods}
    child: dict[tuple, list] = {}
    rows = []
    for w_i, wk in enumerate(WEEKS):
        season = 1 + 0.08 * math.sin(2 * math.pi * w_i / 52)
        for mid, _, _, _, _, _, _, size in MARKETS[1:] + [("REST", "", "", "", "", "", "", REST_SIZE)]:
            if mid == "M4" and wk in LAST4:
                continue                                                     # E3: FreshCo feed stops
            for pid, _, brand, _, cat, *_ in prods.values():
                if pid == "BUT-9" and not (mid == "M3" and wk in LAST4):
                    continue                                                 # E4: new code only after the recode
                if pid == "BUT-1" and mid == "M3" and wk in LAST4:
                    continue                                                 # E4: old code exits at Store 24
                _, _, _, _, vel, price = params[brand]
                key = (mid, "BUT-1" if pid == "BUT-9" else pid)
                acv = acv0.get(key, 60.0) * (1 + 0.02 * math.sin(w_i / 9 + _h(pid) % 7))
                if brand == "Crunchy" and mid == "M1" and wk in LAST4:
                    acv *= 0.5                                               # E1: distribution loss
                if brand == "Choco Bites" and mid == "M1" and wk == AS_OF:
                    acv *= 0.6                                               # E6: latest-week distribution drop
                if brand == "Golden Bake" and mid == "M2" and wk in LAST4:
                    acv = min(100.0, acv * 1.45)                             # E2: distribution gain
                promo = 1.25 if (w_i + _h(pid)) % 9 == 0 else 1.0
                units = size * acv * vel * season * promo * rng.uniform(0.93, 1.07) * 10
                if mid == "M3" and wk == WEEKS[-2]:
                    units *= 2.6                                             # E5: one-week spike
                base_units = units / promo
                value = units * price * (0.9 if promo > 1 else 1.0)
                base_value = base_units * price
                stores = int(acv * 3 * max(size, 0.3))
                row = [round(value, 2), round(units * 0.15, 3), round(units, 3), round(acv, 4),
                       round(base_value, 2), round(base_units, 3), stores]
                if mid != "REST":
                    rows.append((wk, mid, pid, *row, "v1"))
                agg = child.setdefault((wk, pid), [0.0] * 7 + [0.0])
                for i in (0, 1, 2, 4, 5, 6):
                    agg[i] += row[i]
                agg[7] += row[3] * (size if mid != "REST" else REST_SIZE)       # size-weighted ACV
    total_size = sum(m[7] for m in MARKETS[1:]) + REST_SIZE
    for (wk, pid), a in child.items():
        rows.append((wk, PARENT, pid, round(a[0], 2), round(a[1], 3), round(a[2], 3), round(a[7] / total_size, 4),
                     round(a[4], 2), round(a[5], 3), int(a[6]), "v1"))
    return rows


def markets() -> list[tuple]:
    return [m[:7] for m in MARKETS]
