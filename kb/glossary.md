# Glossary

## Share points
A change in share measured in percentage points of share: a brand going from 23.4% to 22.6% share lost 0.8 share
points. Share Radar never describes a share change as a percent, to avoid confusing 0.8 points with 0.8% of the
brand's share.

## Value at stake
The share change times the current category value sales in the same market and period, in local currency. It
says how much money the share change represents and is one of the three gates a shift must pass.

## Gates
A share change becomes a shift worth reporting only if it passes three gates: at least MIN_SHARE_PTS share points,
at least MIN_VALUE_AT_STAKE in value, and a z-score of at least MIN_Z against the brand's own history (the
latest year comparison has no z-score).

## Confidence
How sure Share Radar is that a shift is unusual: the absolute z-score divided by three, capped at one, or 0.5 when
there is no z-score. When anomaly detection flags at least two of the last four weeks, confidence is at least 0.8.

## Score and ranking
Each shift is scored as absolute value at stake times confidence times an artefact factor (1.0 market move,
0.6 mixed, 0.3 possible data effect), with a 1.5 weighting for the focus manufacturer's brands. The top shifts by
score go into the brief.

## Suppression
A shift that was in a recent brief, with the same sign, is not shown again unless it has grown by at least
SUPPRESS_GROWTH. This keeps the brief about what is new.

## Early warning
A lever move in the latest week that the four-week share has not absorbed yet. If the latest week's distribution
share persists, next period's four-week share moves by about the L4W share times the relative change in
distribution share. It is mechanical, with other levers held, not a forecast.
