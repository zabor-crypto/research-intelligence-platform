# Internal Note: Funding-Rate Mean Reversion Carry

Positive control note. Concept: extreme perp funding rates predict reversion
of the perp premium; collect carry while hedged in spot.

## Data

Funding rate history (8-hour intervals) and 1-hour OHLCV for the top-10 liquid
USDT perpetuals plus matching spot markets, 2021-2025.

## Signal

Funding percentile is computed against a rolling 30-day window. Entry when
the current funding rate exceeds a threshold of 0.9 (90th percentile of the
rolling window); the position is short perp / long spot, inverse for funding
below the 10th percentile.

## Entry and Exit

Enter at the funding timestamp following the signal. Exit when the funding
percentile falls below 0.5, or after a 4320-minute time stop (three days).
No leverage beyond 2x on the perp leg.

## Risk and Costs

Basis-leg hedge rebalanced every funding interval; per-pair notional capped
at 5% of equity; kill-switch if perp-spot basis exceeds 3x its rolling
30-day standard deviation. Assumed costs of 7 bps per side taker plus spot
fees; carry must clear costs by 2x to enter.
