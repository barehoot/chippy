#!/usr/bin/env python3
"""Local dry run: the repository's SQL on DuckDB with synthetic data, then the template brief.

  python3 tests/local/run_local.py [--out docs/examples]

Prints the run summary and the SQL test results, and writes synthetic_brief.html / .md. The data is synthetic
(tests/local/synthetic.py): the names are invented and no number is NIQ data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "python")]

import harness as h  # noqa: E402
import local_brief  # noqa: E402

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Share Radar brief (synthetic data)</title>
<style>
body {{ font: 15px/1.5 -apple-system, "Segoe UI", sans-serif; color: #1f1e1c; max-width: 760px; margin: 2rem auto; padding: 0 1rem }}
h1 {{ font-size: 1.35rem }} h2 {{ font-size: 1.1rem; margin-top: 1.6rem }} .meta {{ color: #52514e; font-size: .9rem }}
.fact {{ border-bottom: 1px dotted #898781; cursor: help }}
.note {{ background: #f0efec; padding: .6rem .8rem; border-radius: 6px; font-size: .9rem; color: #52514e }}
</style></head><body>
<p class="note">Example output from <code>tests/local/run_local.py</code>: the repository's SQL run on DuckDB with
synthetic data, and the deterministic template brief (no LLM). Brand, retailer and manufacturer names are invented.
Hover over a number to see the table and column it was read from.</p>
{body}
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    args = ap.parse_args()
    loc = h.build()
    q = lambda s: loc.con.execute(s).fetchall()  # noqa: E731
    print(f"Pipeline: {sum(r[1] == 'OK' for r in loc.log)}/{len(loc.log)} statements ran")
    print("Candidates past the gates:", q("SELECT COUNT_IF(PASSED_GATES) FROM SR_DB.APP.SHIFT_CANDIDATE")[0][0])
    print("Artefact rules fired:", ", ".join(f"{r} on {m}" for r, m in q(
        "SELECT DISTINCT RULE_ID, MARKET_ID FROM SR_DB.APP.ARTEFACT_CHECK ORDER BY 1, 2")))
    print("In the brief:")
    for rank, brand, market, cmp, pts in q("""SELECT r.RANK_NO, r.BRAND, m.MARKET_NAME, r.CMP_CODE, 100 * r.D_SHARE
            FROM SR_DB.APP.SHIFT_RANKED r JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = r.MARKET_ID
            WHERE r.SELECTED ORDER BY r.RANK_NO"""):
        print(f"  {rank}. {brand} in {market}, {cmp}: {pts:+.2f} pts")
    results = {t: h.run_sql_test(loc, t) for t in h.SQL_TESTS}
    print(f"SQL tests: {sum(r[0] for r in results.values())}/{len(results)} passed",
          "; ".join(f"{t} FAILED" for t, r in results.items() if not r[0]))
    pack, llm, violations, md, body = local_brief.brief(loc)
    print(f"Fact pack: {len(pack['facts'])} facts; template brief violations: {len(violations)}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "synthetic_brief.html").write_text(PAGE.format(body=body), encoding="utf-8")
    (out / "synthetic_brief.md").write_text(md, encoding="utf-8")
    print(f"Wrote {out / 'synthetic_brief.html'} and .md")
    return 0 if all(r[0] for r in results.values()) and not violations else 1


if __name__ == "__main__":
    sys.exit(main())
