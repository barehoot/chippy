"""Altair chart builders (L11). Polarity is blue for a gain and red for a loss with a neutral grey total; two-series
charts use categorical slots 1 and 2; status colours only for run states, always next to their text. Every bar sits
on a zero baseline, every bar has a signed value label, and every mark has a tooltip."""
from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd

GAIN, LOSS, TOTAL = "#2a78d6", "#e34948", "#898781"
SERIES = ["#2a78d6", "#eb6834"]                                   # value share, distribution share
STATUS = {"OK": "#0ca30c", "WARN": "#fab219", "FAILED": "#d03b3b", "SKIPPED": "#898781"}
INK_2, AXIS, SHADE = "#52514e", "#c3c2b7", "#f0efec"
TERMS = [("DIST_PTS", "Distribution"), ("VELOCITY_PTS", "Velocity"), ("PRICE_PTS", "Price"), ("PROMO_PTS", "Promo")]


def _num(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def bridge_frame(b: dict) -> pd.DataFrame:
    """One SHARE_BRIDGE row -> (term, pts, kind): the terms its mode has, then 'Total change'. Points throughout."""
    rows = [(label, float(b[col])) for col, label in TERMS if _num(b.get(col)) is not None]
    rows.append(("Total change", 100.0 * float(b["D_SHARE"])))
    df = pd.DataFrame(rows, columns=["term", "pts"])
    df["kind"] = ["total" if t == "Total change" else ("gain" if p >= 0 else "loss") for t, p in zip(df.term, df.pts)]
    return df


def _signed_bars(df: pd.DataFrame, cat: str, val: str, color: alt.Color, tooltip: list, sort: list | str,
                 x_title: str) -> alt.LayerChart:
    y = alt.Y(f"{cat}:N", sort=sort, title=None)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=16).encode(
        y=y, x=alt.X(f"{val}:Q", title=x_title), color=color, tooltip=tooltip)
    pos = alt.Chart(df).transform_filter(f"datum.{val} >= 0").mark_text(align="left", dx=4, color=INK_2).encode(
        y=y, x=f"{val}:Q", text=alt.Text(f"{val}:Q", format="+.2f"))
    neg = alt.Chart(df).transform_filter(f"datum.{val} < 0").mark_text(align="right", dx=-4, color=INK_2).encode(
        y=y, x=f"{val}:Q", text=alt.Text(f"{val}:Q", format="+.2f"))
    zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(color=AXIS).encode(x="x:Q")
    return (bars + pos + neg + zero).properties(height=34 * max(len(df), 1), width="container")


def bridge_bars(b: dict) -> alt.LayerChart:
    df = bridge_frame(b)
    color = alt.Color("kind:N", scale=alt.Scale(domain=["gain", "loss", "total"], range=[GAIN, LOSS, TOTAL]), legend=None)
    tooltip = [alt.Tooltip("term:N", title="Driver"), alt.Tooltip("pts:Q", title="Share points", format="+.2f")]
    return _signed_bars(df, "term", "pts", color, tooltip, list(df.term), "Share points")


def retailer_bars(where_df: pd.DataFrame) -> alt.LayerChart:
    """EXACT_RETAILER rows: TOTAL_PTS by CONTRIBUTOR, sorted by ABS(TOTAL_PTS), gain/loss colours, signed labels,
    zero rule; the tooltip adds PERF_PTS and MIX_PTS."""
    df = where_df[where_df.METHOD == "EXACT_RETAILER"].copy()
    df["kind"] = ["gain" if p >= 0 else "loss" for p in df.TOTAL_PTS]
    order = list(df.assign(a=df.TOTAL_PTS.abs()).sort_values("a", ascending=False).CONTRIBUTOR)
    color = alt.Color("kind:N", scale=alt.Scale(domain=["gain", "loss"], range=[GAIN, LOSS]), legend=None)
    tooltip = [alt.Tooltip("CONTRIBUTOR:N", title="Retailer"), alt.Tooltip("TOTAL_PTS:Q", title="Total", format="+.2f"),
               alt.Tooltip("PERF_PTS:Q", title="Performance", format="+.2f"), alt.Tooltip("MIX_PTS:Q", title="Mix", format="+.2f")]
    return _signed_bars(df, "CONTRIBUTOR", "TOTAL_PTS", color, tooltip, order, "Share points")


def flow_bars(flow_df: pd.DataFrame) -> alt.LayerChart:
    """COUNTERPART by FLOW_PTS in SERIES[0], value labels, no legend; the section title says which way share moved."""
    df = flow_df.copy()
    y = alt.Y("COUNTERPART:N", sort="-x", title=None)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=16, color=SERIES[0]).encode(
        y=y, x=alt.X("FLOW_PTS:Q", title="Share points"),
        tooltip=[alt.Tooltip("COUNTERPART:N", title="Brand"), alt.Tooltip("FLOW_PTS:Q", title="Share points", format=".2f")])
    text = alt.Chart(df).mark_text(align="left", dx=4, color=INK_2).encode(
        y=y, x="FLOW_PTS:Q", text=alt.Text("FLOW_PTS:Q", format=".2f"))
    zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(color=AXIS).encode(x="x:Q")
    return (bars + text + zero).properties(height=30 * max(len(df), 1), width="container")


def period_bounds(as_of: date, cmp_code: str, cur_weeks: int) -> tuple[tuple[date, date], tuple[date, date]]:
    """Current period = the last N weeks to the as-of week; base = the same weeks 52 weeks earlier, or the previous
    N weeks for L4W_VS_PP. Each as (first week end, last week end)."""
    now = (as_of - timedelta(weeks=cur_weeks - 1), as_of)
    shift = timedelta(weeks=cur_weeks if cmp_code == "L4W_VS_PP" else 52)
    return now, (now[0] - shift, now[1] - shift)


def trend_lines(trend_df: pd.DataFrame, now: tuple[date, date], base: tuple[date, date] | None) -> alt.LayerChart:
    """Long format (WEEK_END_DATE, series, pct) on one % axis: value share SERIES[0], distribution share SERIES[1],
    2px lines, legend plus direct labels at the last week, SHADE rectangles for the compared periods,
    crosshair rule with tooltip."""
    long = trend_df.melt(id_vars="WEEK_END_DATE", value_vars=["VALUE_SHARE_PCT", "DIST_SHARE_PCT"],
                         var_name="series", value_name="pct")
    long["series"] = long.series.map({"VALUE_SHARE_PCT": "Value share", "DIST_SHARE_PCT": "Distribution share"})
    color = alt.Color("series:N", scale=alt.Scale(domain=["Value share", "Distribution share"], range=SERIES),
                      legend=alt.Legend(orient="top", title=None))
    x = alt.X("WEEK_END_DATE:T", title=None)
    spans = [{"start": now[0] - timedelta(days=6), "end": now[1], "label": "Now"}]
    if base:
        spans.append({"start": base[0] - timedelta(days=6), "end": base[1], "label": "Before"})
    shade = alt.Chart(pd.DataFrame(spans)).mark_rect(color=SHADE).encode(
        x="start:T", x2="end:T", tooltip=[alt.Tooltip("label:N", title="Compared period")])
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=x, y=alt.Y("pct:Q", title="% of category"), color=color)
    last = long[long.WEEK_END_DATE == long.WEEK_END_DATE.max()]
    labels = alt.Chart(last).mark_text(align="left", dx=6, color=INK_2).encode(
        x=x, y="pct:Q", text=alt.Text("pct:Q", format=".1f"))
    hover = alt.selection_point(fields=["WEEK_END_DATE"], nearest=True, on="pointerover", empty=False)
    rule = alt.Chart(long).mark_rule(color=AXIS).encode(
        x=x, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("WEEK_END_DATE:T", title="Week ending"), alt.Tooltip("series:N"),
                 alt.Tooltip("pct:Q", title="%", format=".2f")]).add_params(hover)
    return (shade + lines + labels + rule).properties(height=260, width="container")


def step_timeline(steps_df: pd.DataFrame) -> alt.Chart:
    """Bars from STARTED_AT to ENDED_AT per STEP, coloured by STATUS with a legend; tooltip: rows written, message."""
    return alt.Chart(steps_df).mark_bar(size=14).encode(
        y=alt.Y("STEP:N", sort=list(steps_df.STEP), title=None),
        x=alt.X("STARTED_AT:T", title=None), x2="ENDED_AT:T",
        color=alt.Color("STATUS:N", scale=alt.Scale(domain=list(STATUS), range=list(STATUS.values())),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["STEP", "STATUS", alt.Tooltip("ROWS_WRITTEN:Q", title="Rows"), "MESSAGE"],
    ).properties(height=22 * max(len(steps_df), 1), width="container")
