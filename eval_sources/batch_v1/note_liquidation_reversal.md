# Internal Note: Liquidation Cascade Reversal on BTC Perpetuals

Positive control note. Concept: extreme forced selling (liquidation cascades)
overshoots; price mean-reverts within hours once the cascade exhausts.

## Data

BTC-USDT perpetual futures 1-minute OHLCV, volume, and liquidation feed
(long/short liquidation notional per minute), 2021-2025.

## Signal

A cascade is flagged when 5-minute liquidation notional exceeds a threshold
of 8 times its rolling 24-hour average and the 5-minute return is in the
bottom 1st percentile. Entry requires a stabilization bar: the next 5-minute
bar closes above its open with volume declining versus the cascade bar.

## Entry and Exit

Enter long after the stabilization bar confirms, counter to the cascade
direction. Exit at the pre-cascade VWAP anchor, or after a 240-minute time
stop. Stop-loss at 1.5x the 60-minute ATR below the cascade low.

## Risk and Costs

Max one cascade trade per day per asset; risk 0.5% of equity per trade;
de-risk during exchange outage windows. Assumed costs of 7 bps per side.
Internal replay over 2022 bear market shows positive expectancy but heavy
tail risk when cascades chain across venues.
