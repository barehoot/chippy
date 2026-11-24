# Data artefact rules

## Why Share Radar checks for data effects
Some share movements come from changes in the data rather than the market: a retailer feed stops, stores are
added to the panel, history is restated or items are recoded. Before a shift reaches a brief, six rules check for
these effects. Any HIGH rule labels the shift POSSIBLE_DATA_EFFECT and holds it back; MEDIUM rules alone label
it MIXED and lower its score; with no rule, it is a MARKET_MOVE.

## R1 coverage change
The store universe of a market changed by more than the ART_STORE_CHG threshold between the two periods (HIGH).
Without store counts, a proxy fires when category distribution per week jumps while category sales per
distribution point stay flat (MEDIUM). What to do: ask Input Validation whether the panel changed.

## R2 retailer feed change
A child retailer has category sales in one period and none in the other, so the parent total moves for a reason
that is not shopper behaviour (HIGH). What to do: confirm the retailer's feed status before reporting the shift.

## R3 restatement
A week inside the compared periods has a different data fingerprint than at the previous run, meaning the data
was restated. HIGH if the restated weeks moved market value by at least ART_RESTATE_PCT, MEDIUM otherwise. What to
do: compare with the previous brief and note the restatement.

## R4 item recode
A brand's exiting items and entering items have about the same sales, each a large part of the brand, which
looks like a recode rather than a range change (MEDIUM). What to do: check the item master for code changes.

## R5 one-week spike
A current week's category sales sit more than ART_SPIKE_K standard deviations away from the trailing 13-week mean
(MEDIUM). What to do: check for a data error or a one-off event such as a festival.

## R6 missing weeks
The category is missing weeks in either period, so the periods are not comparable (HIGH). What to do: wait for
the missing weeks or use a longer comparison.
