"""Number, label and alias formatting (L11). Matches sr_lib.render.format_fact character for character (T-UI-02),
so a number reads the same in the app and in the brief. Imports data lazily, inside name(), so tests need no session."""
from __future__ import annotations

CMP_TEXT = {"L4W_VS_YA": "last 4 weeks vs year ago", "L4W_VS_PP": "last 4 weeks vs previous 4 weeks",
            "L12W_VS_YA": "last 12 weeks vs year ago", "L52W_VS_YA": "last 52 weeks vs year ago"}
CUR_WEEKS = {"L4W_VS_YA": 4, "L4W_VS_PP": 4, "L12W_VS_YA": 12, "L52W_VS_YA": 52}
LABEL_CHIP = {"MARKET_MOVE": "✓ Market move", "MIXED": "◐ Mixed signals", "POSSIBLE_DATA_EFFECT": "⚠ Possible data effect"}
RUN_CHIP = {"SUCCEEDED": "✓ Succeeded", "RUNNING": "… Running", "FAILED": "✕ Failed", "SKIPPED": "– Skipped"}
STATUS_CHIP = {"OK": "✓ OK", "WARN": "! Warn", "FAILED": "✕ Failed", "SKIPPED": "– Skipped"}
GENERATOR_CHIP = {"LLM": "LLM brief", "LLM_RETRY": "LLM brief (retry)", "TEMPLATE": "Template brief"}
RULE_TEXT = {"R1_COVERAGE": "Store coverage change", "R2_FEED": "Retailer feed change", "R3_RESTATE": "Restated data",
             "R4_RECODE": "Item recode", "R5_SPIKE": "One-week spike", "R6_GAP": "Missing weeks"}
_UNITS = ((1e9, "B"), (1e6, "M"), (1e3, "K"))
DASH = "–"


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and x != x)


def pct(share: float | None, d: int = 1) -> str:
    """0.2341 -> '23.4%'."""
    return DASH if _missing(share) else f"{100 * float(share):.{d}f}%"


def pts(points: float | None, d: int = 2) -> str:
    """-0.8412 -> '-0.84 pts' (input already in points)."""
    return DASH if _missing(points) else f"{float(points):+.{d}f} pts"


def money(x: float | None, currency: str, d: int = 1) -> str:
    """-1834220.5 -> '-INR 1.8M'; K, M and B with one decimal; below 1,000 a whole number."""
    if _missing(x):
        return DASH
    sign, a = ("-" if float(x) < 0 else ""), abs(float(x))
    if f"{a:.0f}" == "1000" and a < 1e3:
        a = 1e3
    for i, (unit, suffix) in enumerate(_UNITS):
        if a >= unit:
            text = f"{a / unit:.{d}f}"
            if float(text) >= 1000 and i > 0:
                unit, suffix = _UNITS[i - 1]
                text = f"{a / unit:.{d}f}"
            return f"{sign}{currency} {text}{suffix}"
    return f"{sign}{currency} {a:.0f}"


def signed_pct(ratio: float | None, d: int = 1) -> str:
    """0.031 -> '+3.1%'."""
    return DASH if _missing(ratio) else f"{100 * float(ratio):+.{d}f}%"


def confidence(c: float | None) -> str:
    """>= 0.8 'High', >= 0.5 'Medium', else 'Low', with the value."""
    if _missing(c):
        return DASH
    c = float(c)
    return f"{'High' if c >= 0.8 else 'Medium' if c >= 0.5 else 'Low'} ({c:.2f})"


def name(real: str | None, kind: str = "BRAND") -> str:
    """The alias from APP.V_ALIAS when DISPLAY_ALIAS is true, else the real name."""
    if real is None:
        return DASH
    from sr_ui import data                         # lazy: keeps this module importable without a session
    if data.cfg("DISPLAY_ALIAS") is True:
        return data.aliases().get((kind, real), real)
    return real


def headline(shift: dict, markets: dict[str, str]) -> str:
    """'<Brand> lost 0.84 pts in <Market>, last 4 weeks vs year ago'."""
    d = float(shift["D_SHARE_PTS"] if "D_SHARE_PTS" in shift else 100 * shift["D_SHARE"])
    verb = "lost" if d < 0 else "gained"
    market = markets.get(shift["MARKET_ID"], shift["MARKET_ID"])
    return f"{name(shift['BRAND'])} {verb} {abs(d):.2f} pts in {market}, {CMP_TEXT.get(shift['CMP_CODE'], shift['CMP_CODE'])}"
