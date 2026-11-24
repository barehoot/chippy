# The share bridge

## What the share bridge does
The share bridge splits a brand's change in value share into the business levers that caused it: distribution,
velocity, price and promotion. The terms are in share points and add up exactly to the reported change, with no
residual and no "other" bar.

## How the bridge is calculated
Value share equals distribution share times the velocity index times the price index times the promo index, each
relative to the category. Taking logs turns the product into a sum, and each term is weighted by the logarithmic
mean of the two shares, L(s1, s0) = (s1 - s0) / (ln s1 - ln s0). Each term in points is 100 x L x ln(F1 / F0),
and the terms sum exactly to 100 x (s1 - s0). This is the logarithmic mean Divisia index (LMDI) method.

## Bridge modes A to D
The mode depends on the data available. Mode A needs TDP, base units, base value and value, and gives four terms:
distribution, base unit velocity, base price and promo. Mode B needs TDP, units and value, and gives distribution,
unit velocity and average price. Mode C needs TDP and value, and gives distribution and value velocity. Mode D has
value only: Share Radar reports the share change without a split. The capability check picks the best mode the
data supports each week.

## New listings, delistings and missing data
A brand with no sales in the base period is a new listing, and one with no sales in the current period is
delisted. Neither can be split, because the log of zero is undefined, so the bridge reports the share change and
labels it instead. A missing category total in one period gives the status NO_DATA.

## Reading the terms
Start with the largest term. A large negative distribution term means the brand lost listings or shelf presence.
A negative velocity term means it sells more slowly where it is stocked. A positive price term means its price
moved in a direction that helped value share; it does not say whether volume suffered. The promo term shows the
effect of promotional intensity relative to the category.

## Where it happened: the retailer split
For a shift in the parent market, each retailer contributes a performance term (the change in the brand's share
within that retailer, times the retailer's average weight) and a mix term (the change in the retailer's weight,
times the brand's average share there). The parts add up exactly to the parent change.

## Who took it: share flow
Within one market and comparison, share changes sum to zero. The points a losing brand gave up are allocated to
the gaining brands in proportion to their gains. This is an accounting allocation, not evidence of shoppers
switching between the brands.
