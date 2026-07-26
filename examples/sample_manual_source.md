# Volatility Regime Conditioning of Intraday Momentum in Crypto Markets

## Abstract

We study whether volatility clustering conditions the profitability of
short-horizon momentum in cryptocurrency markets. Using 1-minute and 5-minute
bars for BTC and ETH perpetual futures, we classify realized volatility into
low, medium, and high regimes and measure the performance of simple
trend-following entries within each regime. Momentum profits concentrate in
expanding-volatility regimes, while low-volatility and high-noise regimes are
dominated by mean reversion. A regime switching filter based on rolling
realized volatility materially improves risk-adjusted returns after
transaction costs.

## Data

- BTC-USDT and ETH-USDT perpetual futures, 1-minute OHLCV and volume,
  2020-2024.
- Funding rate history for robustness checks.

## Signal

Realized volatility is computed over rolling 60-minute windows of 1-minute
returns. Regimes are defined by the ratio of short-window to long-window
realized volatility: expanding when the ratio exceeds 1.2, contracting below
0.8. Momentum signal: sign of the past 30-minute return when trend strength
(|return| / realized volatility) exceeds a threshold of 0.5.

## Entry and Exit

Entry: open a position in the direction of the 30-minute return when the
volatility regime is expanding and trend strength exceeds the threshold.
Exit: close when trend strength falls below 0.2, when the regime switches to
contracting, or after a 120-minute time stop. A stop-loss is placed at 1.5x
the 60-minute ATR.

## Risk Management

Position size is normalized by realized volatility to target constant risk per
trade. Portfolio exposure is capped, and trading halts during extreme
drawdown. Transaction costs of 7 bps per side (fees plus slippage) are
included in all results.

## Results

The regime-filtered momentum strategy earns a Sharpe ratio of 1.4 after costs
versus 0.4 unconditional. Profits are robust across both assets and across
2021-2024 subsamples, but decay at holding periods beyond four hours.

## Limitations

Results rely on liquid perpetual futures; thin altcoin markets may behave
differently. The volatility threshold parameters were chosen in-sample and
require walk-forward validation.
