# Internal Note: Volatility-Regime Gated Momentum on ETH Perpetuals

Positive control note. Concept: intraday momentum on ETH perpetual futures is
only profitable when volatility is expanding; a regime filter should gate all
entries.

## Data

ETH-USDT perpetual futures, 1-minute OHLCV and volume, 2021-2025.

## Signal

Realized volatility is computed over a rolling 45-minute window of 1-minute
returns. The regime is expanding when the ratio exceeds 1.3 and contracting
below 0.7 (short-window RV over long-window RV). Momentum is the sign of the
past 15-minute return; trend strength is the absolute return divided by
realized volatility and entries require that it exceeds a threshold of 0.6.

## Entry and Exit

Enter with the direction of the 15-minute return when the regime is expanding
and trend strength exceeds the threshold. Exit when trend strength falls
below 0.25, when the regime turns contracting, or after a 90-minute time
stop. Stop-loss at 2x the 45-minute ATR.

## Risk and Costs

Position size normalized by realized volatility; portfolio volatility target
12% annualized; halt after a 8% monthly drawdown. Assumed costs of 6 bps per
side including slippage. In a rough internal backtest the filtered variant
earns a Sharpe ratio of 1.1 after costs versus 0.3 unconditional.
