---
name: share-methodology
description: The retail measurement method behind Share Radar - ACV, TDP, velocity, value share, the exact LMDI share bridge and its modes, the retailer split, share flow, early warning and the data artefact rules. Use when writing or checking any calculation, a brief, knowledge-base text or an answer about why share moved.
---
# Share methodology

## Definitions
- %ACV distribution of an item: the share of all-commodity volume in stores selling it, 0 to 100.
- TDP (total distribution points) = sum of item %ACV; over a period, also summed across weeks.
- Value share = brand value sales / category value sales, within one market, category and period.
  Shares never add up or average across markets.
- Velocity = sales per TDP point. Price = value per unit. Promo index = actual value / base value.

## The bridge (L6)
- share = distribution share x velocity index x price index x promo index (mode A), each relative to the category.
- Points per term = 100 x L(s1, s0) x ln(F1 / F0), where L(a, b) = (a - b) / (ln a - ln b) and L(a, a) = a.
  The terms add up exactly to the change, so the residual is zero.
- Mode A: TDP, base units, base value, value -> four terms. Mode B: TDP, units, value -> distribution, unit
  velocity, price. Mode C: TDP, value -> distribution, value velocity. Mode D: no terms.
- NEW, EXIT and NO_DATA rows get no terms.

## Where and who
- Retailer split, exact: performance = average weight x change in within-retailer share;
  mix = average share x change in weight.
- Flow: a losing brand's points go to gainers in proportion to their gains. It is an accounting allocation;
  never call it switching.

## Early warning
- If the latest week's distribution share persists, next period's L4W share moves by about
  s(L4W) x (DS latest / DS L4W - 1), other levers held. It is mechanical, not a forecast.

## Data artefact rules (L6)
- R1 coverage, R2 feed, R3 restatement, R4 recode, R5 spike, R6 gap.
- Any HIGH rule -> POSSIBLE_DATA_EFFECT, held back from the brief. MEDIUM only -> MIXED.

## Writing about it
- Name the comparison every time, for example "last 4 weeks vs year ago". Put the largest term first.
- Say "share points" for changes, never "percent". Never state a number that no tool or fact returned.
