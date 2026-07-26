"""Deterministic rule-based LLM client.

Used for tests and offline runs. Keyword/regex heuristics classify strategy
style, timeframe, and HFT dependency, extract concrete numeric parameters
from the source text, and produce parameterized crypto adaptation templates.
Replace with a real provider via LLM_PROVIDER=anthropic|openai for
production-quality extraction.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from research_intel.extraction.schemas import NON_APPLICABLE_HFT, SCORING_DIMENSIONS
from research_intel.llm.base import LLMClient

# ---------------------------------------------------------------- HFT detection

HFT_KEYWORDS = (
    "queue position", "queue-position", "latency arbitrage", "co-location", "colocation",
    "microsecond", "nanosecond", "sub-millisecond", "tick-to-trade", "fpga",
    "matching engine proximity", "high-frequency market making", "quote racing",
    "speed advantage over other participants", "direct feed",
)

# Semantic latency-dependence phrasing that avoids the classic keywords.
HFT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"react\w*\s+within\s+(?:the\s+same|one|a\s+single)\s+(?:order.?book\s+)?(?:update|tick)",
        r"lose\w*\s+(?:its\s+|the\s+)?edge\s+if\s+delayed",
        r"cancel\s+and\s+repost\s+before",
        r"immediate\s+(?:response|reaction)\s+to\s+(?:depth|quote|book|order.?book)\s+(?:change|update)",
        r"first\s+in\s+the\s+(?:book|queue)",
        r"(?:vanish|disappear)\w*\s+when\s+orders\s+are\s+delayed",
        r"delayed\s+(?:by|beyond)\s+(?:one|a|\d+)\s+(?:tick|second|millisecond|microsecond)",
        r"faster\s+than\s+(?:other|competing|the\s+other)",
        r"before\s+competitors?\s+(?:update|react|repric)",
        r"within\s+\d+\s*(?:micro|milli|nano)second",
    )
)

# Papers whose edge is pure speed cannot be adapted; this many distinct HFT
# markers means the mechanism itself is latency, not a slowable signal.
PURE_SPEED_HIT_THRESHOLD = 3
NOT_TRANSFERABLE = "not_transferable_latency_edge"

# ---------------------------------------------------------------- style/timeframe

STYLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "momentum": ("momentum", "trend following", "trend-following", "breakout", "time series momentum"),
    "mean_reversion": ("mean reversion", "mean-reversion", "reversal", "overreaction", "capitulation"),
    "volatility_regime": ("volatility regime", "volatility clustering", "regime switching",
                          "realized volatility", "garch", "volatility targeting"),
    "statistical_arbitrage": ("statistical arbitrage", "pairs trading", "cointegration", "stat arb"),
    "flow_imbalance": ("order flow", "order imbalance", "volume imbalance", "trade imbalance",
                       "order book imbalance", "ofi"),
    "carry_basis": ("funding rate", "basis trading", "perpetual", "carry", "futures basis"),
    "market_making": ("market making", "market-making", "inventory", "bid-ask spread", "quoting"),
    "cross_sectional": ("cross-sectional", "cross sectional", "ranking", "long-short portfolio"),
    "event_driven": ("liquidation cascade", "liquidations", "liquidation", "forced selling",
                     "announcement", "event study", "news"),
    "portfolio_risk": ("risk parity", "portfolio optimization", "drawdown control",
                       "position sizing", "kelly"),
}

TIMEFRAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "1m-15m": ("1-minute", "1 minute", "5-minute", "5 minute", "intraday", "minute-level", "1m", "5m"),
    "1h-4h": ("hourly", "1-hour", "4-hour", "hour-level"),
    "daily": ("daily", "day-level", "end-of-day", "weekly", "monthly"),
}

DATA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ohlcv": ("price", "return", "ohlc", "ohlcv", "candle", "close"),
    "volume": ("volume",),
    "order_book_snapshots": ("order book", "orderbook", "depth", "bid-ask", "quote"),
    "trades": ("trade-level", "tick data", "trades", "order flow"),
    "funding_rates": ("funding",),
    "futures_basis": ("basis",),
    "liquidations": ("liquidation",),
    "cross_sectional_universe": ("cross-sectional", "cross sectional", "universe"),
}

INDICATOR_KEYWORDS = (
    "rsi", "macd", "atr", "bollinger", "moving average", "ema", "sma", "vwap",
    "realized volatility", "z-score", "obv",
)

# ---------------------------------------------------------------- parameter extraction

# name -> list of regex alternatives; first group is the numeric value.
PARAM_PATTERNS: dict[str, tuple[str, ...]] = {
    "rv_window_minutes": (
        r"rolling (\d+)[- ]minute window",
        r"volatility[^.]{0,40}over (?:a )?(\d+)[- ]minute",
    ),
    "vol_expansion_ratio": (
        r"expanding when the ratio exceeds (\d+(?:\.\d+)?)",
        r"ratio exceeds (\d+(?:\.\d+)?)",
    ),
    "vol_contraction_ratio": (
        r"contracting (?:when |if )?below (\d+(?:\.\d+)?)",
        r"contracting[^.]{0,30}below (\d+(?:\.\d+)?)",
    ),
    "momentum_lookback_minutes": (
        r"(?:past|previous|last) (\d+)[- ]minute return",
    ),
    "trend_strength_entry": (
        r"exceeds a threshold of (\d+(?:\.\d+)?)",
        r"entry threshold of (\d+(?:\.\d+)?)",
    ),
    "trend_strength_exit": (
        r"falls below (\d+(?:\.\d+)?)",
        r"exit threshold of (\d+(?:\.\d+)?)",
    ),
    "time_stop_minutes": (
        r"(\d+)[- ]minute time stop",
    ),
    "stop_loss_atr_mult": (
        r"(\d+(?:\.\d+)?)x\s+the [\w-]+ ATR",
        r"stop[- ]loss[^.]{0,30}(\d+(?:\.\d+)?)x",
    ),
    "fee_slippage_bps_per_side": (
        r"(\d+(?:\.\d+)?) bps per side",
        r"costs of (\d+(?:\.\d+)?) (?:bps|basis points)",
    ),
    "lookback_days": (
        r"rolling (\d+)[- ]day (?:window|history|average)",
        r"trailing (\d+)[- ]day",
    ),
    "ret_percentile_entry": (
        r"bottom (\d+)(?:st|nd|rd|th)? percentile",
    ),
}

# ---- source entry-condition extraction (v0.2.1 P4) ----
# (pattern, condition template over the captured groups). Numbers captured in
# the condition are what the fidelity check requires downstream rules to keep.

ENTRY_CONDITION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"exceeds a threshold of (\d+(?:\.\d+)?) times its rolling (\d+)[- ]hour average",
     "liquidation/forced-flow spike > {0}x rolling {1}h average"),
    (r"return is in the (?:bottom|top) (\d+)\w{0,2} percentile",
     "5-minute return in bottom {0} percentile"),
    (r"next (\d+)[- ]minute bar closes above its open",
     "stabilization: next {0}-minute bar closes above its open"),
    (r"volume declining versus the cascade bar",
     "volume declining versus the cascade bar"),
    (r"ratio exceeds (\d+(?:\.\d+)?)",
     "volatility regime expanding: vol_ratio > {0}"),
    (r"trend strength[^.]*?exceeds a threshold of (\d+(?:\.\d+)?)",
     "trend_strength > {0}"),
    (r"(?:direction of|sign of) the (?:past )?(\d+)[- ]minute return",
     "direction of the {0}-minute return"),
    (r"funding rate exceeds a threshold of (\d+(?:\.\d+)?)",
     "funding rate above the {0} percentile threshold"),
)


def extract_entry_conditions(text: str) -> list[str]:
    """Extract the source's distinct entry conditions (positive-control
    archetypes: volatility-regime momentum, funding MR, liquidation reversal)."""
    flat = re.sub(r"\s+", " ", text)
    conditions: list[str] = []
    for pattern, template in ENTRY_CONDITION_PATTERNS:
        match = re.search(pattern, flat, re.IGNORECASE)
        if not match:
            continue
        groups = []
        for g in match.groups():
            if g is None:
                continue
            value: Any = float(g) if "." in g else (int(g) if g.isdigit() else g)
            # Fractional percentiles read as percent (0.9 -> 90).
            if isinstance(value, float) and 0 < value <= 1 and "percentile" in template:
                value = int(value * 100)
            groups.append(value)
        conditions.append(template.format(*groups))
    return conditions

# ---- source fact extraction (v0.2 P4) ----

UNIVERSE_PATTERNS = (
    r"top-\d+ liquid (?:USDT )?perpetuals(?: plus matching spot markets)?",
    r"top-\d+ liquid (?:crypto )?assets",
    r"[A-Z0-9]{2,6}-USDT?(?:\s+and\s+[A-Z0-9]{2,6}-USDT?)* perpetual futures",
)

RISK_PATTERNS: dict[str, tuple[str, ...]] = {
    "portfolio_vol_target_pct": (r"volatility target (?:of )?(\d+(?:\.\d+)?)%",),
    "monthly_drawdown_halt_pct": (r"halt (?:trading )?after an? (\d+(?:\.\d+)?)% monthly drawdown",),
    "risk_per_trade_pct": (r"risk (\d+(?:\.\d+)?)% of equity per trade",),
    "max_trades_per_day": (r"max(?:imum)? (one|\d+) (?:cascade |event )?trades? per day",),
    "max_leverage_x": (
        r"no leverage beyond (\d+(?:\.\d+)?)x",
        r"(\d+(?:\.\d+)?)x max(?:imum)? leverage",
        r"leverage (?:capped|limited) (?:at|to) (\d+(?:\.\d+)?)x",
    ),
    "per_pair_notional_cap_pct": (r"capped at (\d+(?:\.\d+)?)% of equity",),
    "basis_kill_switch_stdev_mult": (
        r"exceeds (\d+(?:\.\d+)?)x its rolling \d+[- ]day standard deviation",
    ),
    "carry_cost_clearance_mult": (r"clear costs by (\d+(?:\.\d+)?)x",),
    "exchange_outage_derisk": (r"(exchange outage)",),
}

COST_PATTERNS: dict[str, tuple[str, ...]] = {
    "fee_slippage_bps_per_side": PARAM_PATTERNS["fee_slippage_bps_per_side"],
}

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3}


def _match_patterns(text_flat: str, patterns: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name, pats in patterns.items():
        for pattern in pats:
            match = re.search(pattern, text_flat, re.IGNORECASE)
            if match:
                value: Any = match.group(1)
                if isinstance(value, str):
                    lower_value = value.lower()
                    if lower_value in WORD_NUMBERS:
                        value = WORD_NUMBERS[lower_value]
                    elif re.fullmatch(r"\d+(?:\.\d+)?", value):
                        value = float(value) if "." in value else int(value)
                    else:
                        value = True  # presence flag (e.g. exchange outage de-risk)
                found[name] = value
                break
    return found


def extract_source_facts(text: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Extract (asset_universe, risk_parameters, cost_parameters) from source text."""
    flat = re.sub(r"\s+", " ", text)
    universe = ""
    for pattern in UNIVERSE_PATTERNS:
        match = re.search(pattern, flat)
        if match:
            universe = match.group(0)
            break
    return universe, _match_patterns(flat, RISK_PATTERNS), _match_patterns(flat, COST_PATTERNS)

METRIC_PATTERNS: dict[str, str] = {
    "sharpe_after_costs": r"Sharpe ratio of (\d+(?:\.\d+)?)",
    "sharpe_unconditional": r"versus (\d+(?:\.\d+)?) unconditional",
    "max_drawdown_pct": r"maximum drawdown of (\d+(?:\.\d+)?)%",
}


def extract_parameters(text: str) -> tuple[dict[str, Any], str]:
    """Regex-extract concrete strategy parameters. Returns (params, quality)."""
    flat = re.sub(r"\s+", " ", text)  # patterns must survive line wrapping
    params: dict[str, Any] = {}
    for name, patterns in PARAM_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, flat, re.IGNORECASE)
            if match:
                value = match.group(1)
                params[name] = float(value) if "." in value else int(value)
                break
    found = len(params)
    total = len(PARAM_PATTERNS)
    quality = (
        "explicit" if found >= total - 2
        else "partially_explicit" if found >= 3
        else "inferred" if found >= 1
        else "missing"
    )
    return params, quality


def extract_reported_metrics(text: str) -> dict[str, Any]:
    flat = re.sub(r"\s+", " ", text)
    metrics: dict[str, Any] = {}
    for name, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, flat, re.IGNORECASE)
        if match:
            metrics[name] = float(match.group(1))
    return metrics


# ---------------------------------------------------------------- adaptation templates
#
# Each template's entry/exit rules are format strings over its `params` dict.
# Source-extracted parameters override defaults where the names match, and
# provenance is recorded per parameter.

VOL_MOMENTUM_PARAMS: dict[str, Any] = {
    "rv_window_minutes": 60,
    "vol_expansion_ratio": 1.2,
    "vol_contraction_ratio": 0.8,
    "momentum_lookback_minutes": 30,
    "trend_strength_entry": 0.5,
    "trend_strength_exit": 0.2,
    "time_stop_minutes": 120,
    "stop_loss_atr_mult": 1.5,
    "fee_slippage_bps_per_side": 7,
}

VOL_MOMENTUM_ENTRY = [
    "Long entry: vol_ratio > {vol_expansion_ratio} AND ret_{momentum_lookback_minutes}m > 0 "
    "AND trend_strength = abs(ret_{momentum_lookback_minutes}m) / rv_{rv_window_minutes}m "
    "> {trend_strength_entry}",
    "Short entry: vol_ratio > {vol_expansion_ratio} AND ret_{momentum_lookback_minutes}m < 0 "
    "AND trend_strength > {trend_strength_entry}",
]
VOL_MOMENTUM_EXIT = [
    "Exit when trend_strength < {trend_strength_exit}",
    "Exit on regime transition: vol_ratio < {vol_contraction_ratio} (expanding -> contracting)",
    "Time stop: exit after {time_stop_minutes} minutes in position",
    "Stop-loss at {stop_loss_atr_mult}x ATR_{rv_window_minutes}m from entry price",
]

ADAPTATIONS: dict[str, dict[str, Any]] = {
    "momentum": {
        "name": "Volatility-Aware Crypto Momentum",
        "core": "Directional persistence in crypto returns is exploitable when conditioned on volatility regime; trend entries only in expanding-volatility regimes.",
        "timeframe": "1m-15m",
        "params": VOL_MOMENTUM_PARAMS,
        "entry": VOL_MOMENTUM_ENTRY,
        "exit": VOL_MOMENTUM_EXIT,
    },
    "volatility_regime": {
        "name": "Realized-Volatility Regime Filter",
        "core": "Volatility regimes condition the profitability of directional signals; use a vol-regime classifier as an overlay that gates entries and scales size.",
        "timeframe": "1m-15m",
        "params": VOL_MOMENTUM_PARAMS,
        "entry": VOL_MOMENTUM_ENTRY,
        "exit": VOL_MOMENTUM_EXIT,
    },
    "mean_reversion": {
        "name": "Crypto Overreaction Mean Reversion",
        "core": "Short-horizon overreactions after abnormal moves revert; fade extreme moves that occur on exhausted volume.",
        "timeframe": "1m-15m",
        "params": {
            "ret_lookback_bars": 12, "zscore_window_bars": 100, "entry_zscore": 2.0,
            "exit_zscore": 0.0, "stop_loss_atr_mult": 1.5, "time_stop_bars": 24,
            "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Enter counter-trend when zscore of ret_{ret_lookback_bars}bars over rolling "
            "{zscore_window_bars} bars exceeds {entry_zscore} in absolute value AND volume < "
            "its rolling {zscore_window_bars}-bar average",
        ],
        "exit": [
            "Exit when zscore crosses {exit_zscore} (reversion target)",
            "Stop-loss at {stop_loss_atr_mult}x ATR_14 from entry",
            "Time stop: exit after {time_stop_bars} bars",
        ],
    },
    "statistical_arbitrage": {
        "name": "Crypto Pairs Stat-Arb",
        "core": "Cointegrated crypto pairs exhibit tradable spread mean reversion at hourly horizons.",
        "timeframe": "1h-4h",
        "params": {
            "coint_window_days": 90, "universe_size": 50, "entry_zscore": 2.0,
            "exit_zscore": 0.0, "stop_zscore": 4.0, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Enter spread position when spread z-score over rolling {coint_window_days}-day "
            "window > {entry_zscore} (pairs pre-selected by cointegration test over "
            "top-{universe_size} liquid assets)",
        ],
        "exit": [
            "Exit when spread z-score crosses {exit_zscore}",
            "Stop-out at spread z-score > {stop_zscore} or on cointegration break",
        ],
    },
    "flow_imbalance": {
        "name": "Aggregated Flow Imbalance Signal",
        "core": "Order-flow/volume imbalance aggregated to 1m-5m bars predicts short-horizon returns without requiring latency edge.",
        "timeframe": "1m-15m",
        "params": {
            "imbalance_window_bars": 20, "entry_zscore": 1.5, "exit_horizon_bars": 10,
            "stop_loss_atr_mult": 1.5, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Enter in direction of imbalance when rolling {imbalance_window_bars}-bar "
            "signed-volume imbalance z-score > {entry_zscore} (aggregated to 1m bars)",
        ],
        "exit": [
            "Time stop: exit after {exit_horizon_bars} bars",
            "Exit early on imbalance z-score sign flip through 0",
            "Stop-loss at {stop_loss_atr_mult}x ATR_14",
        ],
    },
    "carry_basis": {
        "name": "Funding/Basis Carry Harvest",
        "core": "Extreme funding rates and basis levels predict mean reversion in perp premium; harvest carry with directional hedging.",
        "timeframe": "1h-4h",
        "params": {
            "funding_entry_percentile": 90, "funding_exit_percentile": 50,
            "funding_lookback_days": 30, "rebalance_hours": 8,
            "time_stop_minutes": 4320, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Enter short perp / long spot when current funding rate > "
            "{funding_entry_percentile}th percentile of its rolling {funding_lookback_days}-day "
            "history (inverse for negative funding)",
        ],
        "exit": [
            "Exit when funding rate < {funding_exit_percentile}th percentile of the rolling "
            "{funding_lookback_days}-day window",
            "Time stop: exit after {time_stop_minutes} minutes in position",
            "Rebalance hedge every {rebalance_hours} hours at the funding interval",
        ],
    },
    "market_making": {
        "name": "Slow Inventory-Aware Quoting Module",
        "core": "Spread capture with inventory-risk-based quote skew is viable at seconds-to-minutes cadence when spreads are wide relative to volatility.",
        "timeframe": "1m-15m",
        "params": {
            "quote_refresh_seconds": 30, "spread_vol_mult": 2.0, "inventory_limit_pct": 5,
            "vol_window_minutes": 60, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Quote both sides only when book_spread > {spread_vol_mult}x rv_"
            "{vol_window_minutes}m; refresh quotes every {quote_refresh_seconds} seconds and "
            "skew against current inventory",
        ],
        "exit": [
            "Withdraw quotes and unwind passively when inventory > {inventory_limit_pct}% of "
            "capital (hard stop)",
            "Exit on regime transition: withdraw quotes when rv_{vol_window_minutes}m regime "
            "turns high-volatility",
        ],
    },
    "cross_sectional": {
        "name": "Crypto Cross-Sectional Rotation",
        "core": "Cross-sectional ranking effects documented in equities transfer to liquid crypto universes at daily horizons.",
        "timeframe": "daily",
        "params": {
            "universe_size": 20, "rank_lookback_days": 30, "rebalance_days": 7,
            "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Rank top-{universe_size} liquid assets by {rank_lookback_days}-day past return; "
            "enter long top decile and short bottom decile when the ranking-characteristic "
            "spread > 0",
        ],
        "exit": [
            "Time stop: close all positions at each {rebalance_days}-day rebalance",
            "Kill-switch stop-loss on universe-wide drawdown",
        ],
    },
    "event_driven": {
        "name": "Liquidation/Event Reversal",
        "core": "Forced-flow events (liquidation cascades, capitulation volume) create temporary dislocations that revert within hours.",
        "timeframe": "1m-15m",
        "params": {
            "volume_spike_mult": 5, "ret_percentile_entry": 1,
            "time_stop_minutes": 240, "stop_loss_atr_mult": 1.5,
            "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Enter counter-direction when liq_spike_ratio = liq_5m / liq_baseline_24h > "
            "{volume_spike_mult} (liquidation / forced-selling spike vs rolling 24h average)",
            "AND ret_5m_percentile <= {ret_percentile_entry} (5-minute return in bottom "
            "{ret_percentile_entry} percentile of the rolling distribution)",
            "AND stabilization: the next 5-minute bar closes above its open with volume "
            "declining versus the cascade bar",
        ],
        "exit": [
            "Exit at pre-event VWAP anchor (take-profit)",
            "Time stop: exit after {time_stop_minutes} minutes",
            "Stop-loss at {stop_loss_atr_mult}x ATR_60m below the event extreme (cascade low)",
        ],
    },
    "portfolio_risk": {
        "name": "Risk Overlay / Sizing Framework",
        "core": "Volatility-targeted sizing and drawdown-based de-risking improve risk-adjusted returns of any underlying signal set.",
        "timeframe": "daily",
        "params": {
            "vol_target_pct": 15, "vol_window_days": 30, "drawdown_derisk_pct": 10,
            "derisk_fraction_pct": 50, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Overlay on an existing strategy: scale exposure so rolling {vol_window_days}-day "
            "realized portfolio volatility > target is impossible — size = "
            "{vol_target_pct}% / realized_vol",
        ],
        "exit": [
            "De-risk {derisk_fraction_pct}% when rolling {vol_window_days}-day drawdown > "
            "{drawdown_derisk_pct}%; re-risk on recovery (drawdown rule)",
        ],
    },
    "generic": {
        "name": "Crypto Adaptation Candidate",
        "core": "The documented effect may transfer to liquid crypto markets at non-HFT horizons; test the closest crypto analog.",
        "timeframe": "1h-4h",
        "params": {
            "signal_lookback_bars": 20, "entry_threshold": 1.0, "exit_horizon_bars": 10,
            "stop_loss_atr_mult": 1.5, "fee_slippage_bps_per_side": 7,
        },
        "entry": [
            "Reconstruct the source's main signal on crypto OHLCV; enter when the signal "
            "z-score over rolling {signal_lookback_bars} bars > {entry_threshold}",
        ],
        "exit": [
            "Time stop: exit after {exit_horizon_bars} bars",
            "Stop-loss at {stop_loss_atr_mult}x ATR_14",
        ],
    },
}


# Constraints the backtester must enforce over per-parameter grids.
STYLE_CONSTRAINTS: dict[str, list[str]] = {
    "momentum": [
        "vol_expansion_ratio > vol_contraction_ratio",
        "trend_strength_entry > trend_strength_exit",
        "time_stop_minutes > momentum_lookback_minutes",
    ],
    "volatility_regime": [
        "vol_expansion_ratio > vol_contraction_ratio",
        "trend_strength_entry > trend_strength_exit",
        "time_stop_minutes > momentum_lookback_minutes",
    ],
    "mean_reversion": ["entry_zscore > exit_zscore"],
    "statistical_arbitrage": ["stop_zscore > entry_zscore", "entry_zscore > exit_zscore"],
    "carry_basis": ["funding_entry_percentile > funding_exit_percentile"],
}


def _feature_formulas(style: str, p: dict[str, Any]) -> dict[str, str]:
    """Computable feature definitions, parameterized by the merged params."""
    if style in ("momentum", "volatility_regime"):
        lookback = p["momentum_lookback_minutes"]
        window = p["rv_window_minutes"]
        long_window = int(window) * 4
        return {
            f"ret_{lookback}m": f"close / close.shift({lookback}) - 1 (on 1m bars)",
            f"rv_{window}m": f"std(1m log returns over {window} bars) * sqrt({window})",
            "vol_ratio": f"rv_{window}m / rv_{long_window}m (short/long realized volatility)",
            "trend_strength": f"abs(ret_{lookback}m) / rv_{window}m",
            f"atr_{window}m": f"average true range over {window} 1m bars",
        }
    if style == "flow_imbalance":
        window = p["imbalance_window_bars"]
        return {
            "signed_volume": "buy_volume - sell_volume per 1m bar (tick-rule if no side flag)",
            "imbalance_z": f"zscore(rolling sum of signed_volume over {window} bars)",
        }
    if style == "carry_basis":
        days = p["funding_lookback_days"]
        return {
            "funding_percentile": f"percentile rank of current funding vs rolling {days}-day history",
        }
    if style == "mean_reversion":
        return {
            f"ret_{p['ret_lookback_bars']}bars": f"close / close.shift({p['ret_lookback_bars']}) - 1",
            "zscore": f"(ret - rolling mean) / rolling std over {p['zscore_window_bars']} bars",
        }
    if style == "event_driven":
        return {
            "liq_5m": "rolling 5m liquidation notional (sum of liquidation feed per 5m bar)",
            "liq_baseline_24h": "rolling 24h mean of 5m liquidation notional",
            "liq_spike_ratio": "liq_5m / liq_baseline_24h",
            "ret_5m": "close_5m / close_5m.shift(1) - 1",
            "ret_5m_percentile": "rolling percentile rank of ret_5m",
            "stabilization": "next 5m close > open AND volume < cascade_bar_volume",
            "atr_60m": "average true range over 60 minutes",
        }
    return {}


def _build_position_sizing(
    archetype: str,
    params: dict[str, Any],
    risk: dict[str, Any],
    risk_provenance: dict[str, str],
) -> str:
    """Position sizing driven by source risk facts, never generic defaults
    when source values exist (v0.2.1 P2)."""
    if archetype in ("funding_rate_mean_reversion", "basis_carry") and (
        "max_leverage_x" in risk or "per_pair_notional_cap_pct" in risk
    ):
        parts = ["hedged perp/spot notional sized per pair"]
        if "per_pair_notional_cap_pct" in risk:
            parts.append(f"per-pair notional <= {risk['per_pair_notional_cap_pct']}% of equity")
        if "max_leverage_x" in risk:
            parts.append(f"perp leg leverage <= {risk['max_leverage_x']}x")
        parts.append(
            "no ATR stop (position is hedged); an ATR-based stop may be added only "
            "as an optional non-source robustness variant"
        )
        return "; ".join(parts)
    risk_pct = risk.get("risk_per_trade_pct", 1)
    atr_mult = params.get("stop_loss_atr_mult", 1.5)
    atr_window = params.get("rv_window_minutes", 60)
    base = (
        f"risk {risk_pct}% of equity per trade using stop distance "
        f"{atr_mult}x ATR_{atr_window}m"
    )
    if archetype == "liquidation_reversal":
        base += " below the cascade low"
    vol_target = risk.get("portfolio_vol_target_pct")
    if vol_target is not None and (
        archetype == "volatility_regime_momentum"
        or risk_provenance.get("portfolio_vol_target_pct") == "source"
    ):
        base = (
            f"size normalized by realized volatility to target {vol_target}% annualized "
            f"portfolio volatility; " + base
        )
    return base


def _build_minimum_viable_backtest(
    primary_universe: str,
    robustness_universe: str,
    timeframe: str,
    data: list[str],
) -> str:
    """Source-faithful universe is always the primary backtest (v0.2.1 P3)."""
    data_str = " + ".join(data[:4]) if data else "ohlcv"
    text = (
        f"Primary: {primary_universe}, {timeframe} bars ({data_str}), over >=3 years "
        "including one bear market."
    )
    if robustness_universe:
        text += f" Optional robustness: {robustness_universe}."
    text += (
        " Compare vs the baseline set (buy-and-hold, randomized-entry, "
        "unconditional variant)."
    )
    return text


def _optimization_grid(params: dict[str, Any]) -> dict[str, list[Any]]:
    """Small grid around each rule parameter, keyed by the parameter's name."""
    grid: dict[str, list[Any]] = {}
    for name, value in params.items():
        if name == "fee_slippage_bps_per_side" or not isinstance(value, int | float):
            continue
        if isinstance(value, int):
            low, high = max(1, round(value * 0.5)), round(value * 1.5)
            grid[name] = sorted({low, value, high})
        else:
            grid[name] = sorted({round(value * 0.5, 2), value, round(value * 1.5, 2)})
    return grid


def _stable_id(text: str, prefix: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"


def _hypothesis_id(extraction: dict[str, Any], archetype: str, name: str) -> str:
    """Deterministic id from source/document identity, never title alone (P6)."""
    content_hash = hashlib.sha1(
        (extraction.get("signal_description", "") + extraction.get("entry_logic", ""))
        .encode("utf-8")
    ).hexdigest()[:8]
    key = "|".join([
        str(extraction.get("source_id", "")),
        str(extraction.get("document_id", "")),
        extraction.get("title", ""),
        content_hash,
        name,
        archetype,
    ])
    return _stable_id(key, "hyp")


# Rule text for source risk facts; anything not listed renders generically.
RISK_RULE_TEXT = {
    "portfolio_vol_target_pct": "portfolio-level volatility target {v}% annualized",
    "monthly_drawdown_halt_pct": "halt trading after {v}% monthly drawdown",
    "risk_per_trade_pct": "max position risk {v}% of equity per trade",
    "max_trades_per_day": "max {v} event trade(s) per day per asset",
    "max_leverage_x": "leverage capped at {v}x",
    "per_pair_notional_cap_pct": "per-pair notional capped at {v}% of equity",
    "basis_kill_switch_stdev_mult": "kill-switch when basis exceeds {v}x its rolling stdev",
    "carry_cost_clearance_mult": "enter only when expected carry clears costs by {v}x",
    "exchange_outage_derisk": "de-risk during exchange outage windows",
}

DEFAULT_RISK_PARAMS = {
    "risk_per_trade_pct": 1,
    "portfolio_vol_target_pct": 15,
    "drawdown_derisk_30d_pct": 10,
}
DEFAULT_RISK_TEXT = {
    "risk_per_trade_pct": "max position risk 1% of equity per trade",
    "portfolio_vol_target_pct": "portfolio-level volatility target 15% annualized",
    "drawdown_derisk_30d_pct": "de-risk 50% when 30-day drawdown exceeds 10%",
}


def _build_risk_rules(source_risk: dict[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, str]]:
    """Source risk facts override defaults; defaults never overwrite source facts."""
    rules: list[str] = []
    generated: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for key, value in source_risk.items():
        template = RISK_RULE_TEXT.get(key, key.replace("_", " ") + ": {v}")
        display = "" if value is True else value
        rules.append(template.format(v=display).replace("  ", " ").strip() + " (source)")
        generated[key] = value
        provenance[key] = "source"
    for key, value in DEFAULT_RISK_PARAMS.items():
        if key in generated:
            continue
        # Skip the generic vol-target default when the source set its own,
        # and the generic drawdown default when the source has a halt rule.
        if key == "portfolio_vol_target_pct" and "portfolio_vol_target_pct" in generated:
            continue
        if key == "drawdown_derisk_30d_pct" and "monthly_drawdown_halt_pct" in generated:
            continue
        if key == "risk_per_trade_pct" and "risk_per_trade_pct" in generated:
            continue
        rules.append(DEFAULT_RISK_TEXT[key] + " (default)")
        generated[key] = value
        provenance[key] = "default"
    return rules, generated, provenance


def _count_kw(text_lower: str, keyword: str) -> int:
    """Whole-word keyword count ('ofi' must not match inside 'profitable')."""
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text_lower))


def _find_style(text_lower: str) -> str:
    best_style, best_hits = "generic", 0
    for style, keywords in STYLE_KEYWORDS.items():
        hits = sum(_count_kw(text_lower, kw) for kw in keywords)
        if hits > best_hits:
            best_style, best_hits = style, hits
    return best_style


def _hft_markers(text: str, text_lower: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)  # phrases must survive line wrapping
    hits = [kw for kw in HFT_KEYWORDS if _count_kw(text_lower, kw)]
    hits.extend(p.pattern for p in HFT_PATTERNS if p.search(flat))
    return hits


def _parameterization_status(extraction: dict[str, Any]) -> str:
    quality = extraction.get("parameter_source_quality", "missing")
    if quality == "explicit":
        return "source_parameterized"
    if quality == "partially_explicit":
        return "partially_source_parameterized"
    if quality == "inferred":
        return "default_parameterized"
    # No parameters at all: unparameterized when the source also lacks
    # backtestable rules/data; otherwise the idea exists but runs on defaults.
    if (
        extraction.get("backtestability") in ("low", "not_backtestable")
        or extraction.get("source_rule_quality") in ("vague", "missing")
    ):
        return "unparameterized"
    return "default_parameterized"


def _missing_for_backtest(extraction: dict[str, Any]) -> list[str]:
    params = extraction.get("extracted_parameters") or {}
    missing: list[str] = []
    if not any("entry" in k or "threshold" in k for k in params):
        missing.append("entry threshold")
    if not any("lookback" in k or "window" in k for k in params):
        missing.append("lookback window")
    if extraction.get("source_rule_quality") in ("vague", "missing"):
        missing.append("exit condition")
        missing.append("codable entry/exit rules")
    if not extraction.get("risk_management"):
        missing.append("risk rule")
    if extraction.get("transaction_cost_assumptions") in ("", "not discussed"):
        missing.append("transaction cost assumptions")
    if not extraction.get("data_requirements"):
        missing.append("required data specification")
    return missing


def _merge_params(
    defaults: dict[str, Any], extracted: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Overlay source-extracted parameters on template defaults, with provenance."""
    merged = dict(defaults)
    provenance = {name: "default" for name in defaults}
    for name, value in extracted.items():
        if name in merged:
            merged[name] = value
            provenance[name] = "source"
    return merged, provenance


class MockLLMClient(LLMClient):
    """Keyword/regex-heuristic implementation of the LLM interface."""

    def extract_research(
        self,
        text: str,
        schema: dict[str, Any],
        *,
        source_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        # source_id/document_id are audit context only; the extractor stamps
        # the authoritative ids onto the payload afterwards.
        lower = text.lower()
        style = _find_style(lower)
        template = ADAPTATIONS.get(style, ADAPTATIONS["generic"])
        hft_hits = _hft_markers(text, lower)
        # Explicit non-HFT statements neutralize weak single-marker matches.
        non_hft_claim = bool(re.search(r"without (low.|)latency|no latency edge|non.hft", lower))
        hft_dependency = len(hft_hits) >= (2 if non_hft_claim else 1)

        timeframe = next(
            (tf for tf, kws in TIMEFRAME_KEYWORDS.items() if any(k in lower for k in kws)),
            "unspecified",
        )
        data_reqs = [
            name for name, kws in DATA_KEYWORDS.items()
            if any(_count_kw(lower, k) for k in kws)
        ]
        indicators = [ind for ind in INDICATOR_KEYWORDS if ind in lower]

        extracted_params, param_quality = extract_parameters(text)
        reported_metrics = extract_reported_metrics(text)
        source_universe, source_risk, source_cost = extract_source_facts(text)
        merged, _ = _merge_params(template["params"], extracted_params)

        title = next((ln.strip().lstrip("# ") for ln in text.splitlines() if ln.strip()), "untitled")

        has_rules = any(w in lower for w in ("entry", "exit", "threshold", "signal", "when "))
        backtestability = (
            "not_backtestable" if not data_reqs
            else "high" if has_rules and timeframe != "unspecified"
            else "medium" if has_rules
            else "low"
        )

        # Grounding metadata: how concrete are the source's own rules/data?
        if has_rules and param_quality == "explicit":
            rule_quality = "explicit"
        elif has_rules and param_quality in ("partially_explicit", "inferred"):
            rule_quality = "partial"
        elif has_rules:
            rule_quality = "vague"
        else:
            rule_quality = "missing"
        if data_reqs and timeframe != "unspecified":
            data_quality = "explicit"
        elif data_reqs:
            data_quality = "partial"
        else:
            data_quality = "missing"
        if (
            "abstract" in lower and len(text) > 1200
            and ("data" in lower or "results" in lower)
        ):
            evidence_type = "full_paper"
        elif len(text) < 900:
            evidence_type = "abstract_only"
        else:
            evidence_type = "manual_note"
        # Only grounded sources get the adaptation template's rule mechanics;
        # vague sources must not receive fake concrete logic.
        grounded_rules = rule_quality in ("explicit", "partial")

        first_para = text.strip().split("\n\n")[0][:400]
        return {
            "source_id": "",  # filled by the extractor with real DB ids
            "document_id": "",
            "title": title[:200],
            "research_domain": "market_microstructure" if style in ("flow_imbalance", "market_making")
            else "quantitative_finance",
            "asset_class": "crypto" if "crypto" in lower or "bitcoin" in lower or "btc" in lower
            else "equities" if "equit" in lower or "stock" in lower else "multi_asset",
            "market_type": "perpetual_futures" if "perpetual" in lower or "funding" in lower
            else "spot",
            "timeframe": timeframe,
            "strategy_style": style,
            "alpha_mechanism": template["core"],
            "signal_description": first_para,
            "features": data_reqs,
            "indicators": indicators,
            "entry_logic": "; ".join(r.format_map(merged) for r in template["entry"])
            if grounded_rules else "",
            "exit_logic": "; ".join(r.format_map(merged) for r in template["exit"])
            if grounded_rules else "",
            "risk_management": "stop-loss and regime-based de-risking mentioned"
            if "stop" in lower or "drawdown" in lower else "",
            "position_sizing": "volatility targeting" if "volatility target" in lower
            or "position siz" in lower or "normalized by realized volatility" in lower else "",
            "data_requirements": data_reqs or ["ohlcv"],
            "extracted_parameters": extracted_params,
            "parameter_source_quality": param_quality,
            "source_rule_quality": rule_quality,
            "source_data_quality": data_quality,
            "source_evidence_type": evidence_type,
            "source_asset_universe": source_universe,
            "source_risk_parameters": source_risk,
            "source_cost_parameters": source_cost,
            "source_entry_conditions": extract_entry_conditions(text),
            "transaction_cost_assumptions": (
                f"{extracted_params['fee_slippage_bps_per_side']} bps per side (from source)"
                if "fee_slippage_bps_per_side" in extracted_params
                else "explicit costs modeled" if "transaction cost" in lower
                or "slippage" in lower or "fees" in lower else "not discussed"
            ),
            "market_regime_conditions": "volatility-regime dependent" if "regime" in lower else "",
            "reported_metrics": reported_metrics,
            "limitations": (["results may not survive transaction costs"]
                            if "transaction cost" not in lower else []),
            "implementation_complexity": "low" if style in ("momentum", "mean_reversion")
            else "medium",
            "crypto_transferability": (
                NOT_TRANSFERABLE
                if hft_dependency and len(hft_hits) >= PURE_SPEED_HIT_THRESHOLD
                else "direct" if "crypto" in lower else "adaptation_required"
            ),
            "hft_or_low_latency_dependency": hft_dependency,
            "non_applicable_reason": NON_APPLICABLE_HFT if hft_dependency else "",
            "backtestability": backtestability,
            "falsification_tests": [
                "signal has no predictive power out-of-sample",
                "edge disappears after realistic fees and slippage",
            ],
            "notes": f"mock extraction; style={style}; hft markers: {hft_hits}; "
            f"params found: {sorted(extracted_params)}",
        }

    def generate_hypothesis(self, extraction: dict[str, Any]) -> dict[str, Any]:
        from research_intel.hypotheses.fidelity import (
            STYLE_TO_ARCHETYPE,
            derive_source_archetype,
        )

        style = extraction.get("strategy_style") or "generic"
        # Archetype-aware routing (P3): distinctive source data picks the
        # template, not just style keywords.
        source_archetype = derive_source_archetype(extraction)
        template_style = style
        if source_archetype == "liquidation_reversal":
            template_style = "event_driven"
        template = ADAPTATIONS.get(template_style, ADAPTATIONS["generic"])
        generated_archetype = (
            "liquidation_reversal"
            if source_archetype == "liquidation_reversal" and template_style == "event_driven"
            else source_archetype
            if template_style == "carry_basis"
            and source_archetype in ("funding_rate_mean_reversion", "basis_carry")
            else STYLE_TO_ARCHETYPE.get(template_style, "unknown")
        )
        source_hft = bool(extraction.get("hft_or_low_latency_dependency"))
        # Flow and MM ideas can be slowed to 1m+ bars — unless the extraction
        # says the edge itself is latency (pure speed).
        adaptable = (
            style in ("market_making", "flow_imbalance")
            and extraction.get("crypto_transferability") != NOT_TRANSFERABLE
        )
        adapted = source_hft and adaptable
        still_hft = source_hft and not adaptable

        title = extraction.get("title", "untitled")
        hypothesis_id = _hypothesis_id(extraction, generated_archetype, template["name"])

        source_timeframe = extraction.get("timeframe") or ""
        if source_timeframe in ("", "unspecified"):
            timeframe = template["timeframe"]
            timeframe_provenance = "default"
            source_timeframe = ""
        else:
            timeframe = source_timeframe
            timeframe_provenance = "source"

        source_universe = extraction.get("source_asset_universe", "") or ""
        source_risk = extraction.get("source_risk_parameters", {}) or {}
        source_cost = extraction.get("source_cost_parameters", {}) or {}

        parameterization = _parameterization_status(extraction)
        if still_hft:
            status = "rejected_hft"
        elif parameterization == "unparameterized":
            status = "rejected_unbacktestable"
        elif parameterization == "default_parameterized":
            status = "review_only"
        else:
            status = "candidate"

        if status in ("review_only", "rejected_unbacktestable"):
            from research_intel.hypotheses.fidelity import assess_fidelity

            # Do NOT synthesize a concrete template strategy from a vague
            # source: no fake source-derived parameters, no codable rules.
            missing = _missing_for_backtest(extraction)
            review_entry = [
                "REVIEW ONLY: source does not specify a codable entry rule; "
                f"missing: {', '.join(missing) or 'concrete mechanics'}"
            ]
            fid = assess_fidelity(extraction, review_entry, "unknown")
            from research_intel.hypotheses.fidelity import assess_entry_conditions

            cond_fid = assess_entry_conditions(extraction, review_entry)
            return dict(fid) | dict(cond_fid) | {
                "hypothesis_id": hypothesis_id,
                "source_ids": [extraction.get("source_id", "")],
                "hypothesis_name": f"UNGROUNDED IDEA: {template['name']} (from: {title[:60]})",
                "one_sentence_idea": template["core"],
                "market": "crypto",
                "asset_universe": "",
                "timeframe": timeframe,
                "strategy_style": style,
                "core_alpha_hypothesis": template["core"],
                "required_data": list(extraction.get("data_requirements", []) or []),
                "features": [],
                "source_asset_universe": source_universe,
                "source_timeframe": source_timeframe,
                "source_risk_parameters": source_risk,
                "source_cost_parameters": source_cost,
                "entry_rules": review_entry,
                "exit_rules": ["REVIEW ONLY: source does not specify a codable exit rule"],
                "risk_rules": ["REVIEW ONLY: source specifies no risk management"],
                "position_sizing": "",
                "fees_slippage_model": "",
                "strategy_parameters": {},
                "parameter_provenance": {},
                "feature_formulas": {},
                "parameter_source_quality": extraction.get("parameter_source_quality", "missing"),
                "parameterization_status": parameterization,
                "missing_for_backtest": missing,
                "candidate_export_allowed": False,
                "backtest_spec_export_allowed": False,
                "source_reported_metrics": extraction.get("reported_metrics", {}) or {},
                "order_assumptions": "",
                "baseline_comparisons": [],
                "optimization_constraints": [],
                "expected_failure_modes": [],
                "minimum_viable_backtest": "",
                "optimization_parameters": {},
                "walk_forward_validation_plan": "",
                "anti_overfitting_checks": [],
                "priority_score": 0,
                "status": status,
                "hft_or_low_latency_dependency": False,
                "non_applicable_reason": "",
                "original_source_has_latency_dependency": source_hft,
                "adapted_to_non_hft": adapted,
                "adaptation_validity": "strong" if adapted else "not_needed",
                "non_hft_adaptation": (
                    "signal aggregated to 1m+ bars / quoting slowed to minutes cadence; "
                    "edge re-based on inventory/flow information, not reaction speed"
                    if adapted else ""
                ),
            }

        from research_intel.extraction.normalization import normalize_strategy_parameters
        from research_intel.hypotheses.fidelity import assess_fidelity

        norm = normalize_strategy_parameters(
            extraction.get("extracted_parameters", {}) or {},
            source_archetype,
            template_params=template["params"],
        )
        params = dict(template["params"])
        params.update(norm.parameters)
        provenance = {name: "default" for name in template["params"]}
        provenance.update(dict.fromkeys(norm.parameters, "source"))
        entry_rules = [r.format_map(params) for r in template["entry"]]
        exit_rules = [r.format_map(params) for r in template["exit"]]
        fee = params.get("fee_slippage_bps_per_side", 7)

        # Source facts (P4): the source's universe/timeframe/risk/cost numbers
        # override platform defaults, never the other way around.
        default_universe = ("BTC, ETH + top-20 liquid alts"
                           if template_style in ("cross_sectional", "statistical_arbitrage")
                           else "BTC, ETH perpetuals")
        if source_universe:
            asset_universe = source_universe
            universe_provenance = "source"
            robustness_universe = "BTC/ETH perpetuals"
        else:
            asset_universe = default_universe
            universe_provenance = "default"
            robustness_universe = ""
        risk_rules, generated_risk, risk_provenance = _build_risk_rules(source_risk)
        generated_cost = {"fee_slippage_bps_per_side": fee}
        cost_provenance = {
            "fee_slippage_bps_per_side": "source"
            if "fee_slippage_bps_per_side" in source_cost else "default"
        }
        fid = assess_fidelity(extraction, entry_rules, generated_archetype)
        from research_intel.hypotheses.fidelity import assess_entry_conditions

        cond_fid = assess_entry_conditions(extraction, entry_rules)
        position_sizing = _build_position_sizing(
            generated_archetype, params, generated_risk, risk_provenance
        )

        data = list(dict.fromkeys(extraction.get("data_requirements", []) or ["ohlcv"]))
        payload = dict(fid) | dict(cond_fid) | {
            "hypothesis_id": hypothesis_id,
            "source_ids": [extraction.get("source_id", "")],
            "hypothesis_name": f"{template['name']} (from: {title[:60]})",
            "one_sentence_idea": template["core"],
            "market": "crypto",
            "asset_universe": asset_universe,
            "source_asset_universe": source_universe,
            "generated_asset_universe": asset_universe,
            "asset_universe_provenance": universe_provenance,
            "optional_robustness_universe": robustness_universe,
            "timeframe": timeframe,
            "source_timeframe": source_timeframe,
            "generated_timeframe": timeframe,
            "timeframe_provenance": timeframe_provenance,
            "source_risk_parameters": source_risk,
            "generated_risk_parameters": generated_risk,
            "risk_parameter_provenance": risk_provenance,
            "source_cost_parameters": source_cost,
            "generated_cost_parameters": generated_cost,
            "cost_parameter_provenance": cost_provenance,
            "unmapped_extracted_parameters": norm.unmapped,
            "strategy_style": template_style,
            "core_alpha_hypothesis": template["core"],
            "required_data": data,
            "features": extraction.get("features", []) or data,
            "entry_rules": entry_rules,
            "exit_rules": exit_rules,
            "risk_rules": risk_rules,
            "position_sizing": position_sizing,
            "fees_slippage_model": f"taker {fee} bps per side (fees + slippage); "
            "maker 1 bp where passive fills are realistic",
            "strategy_parameters": params,
            "parameter_provenance": provenance,
            "feature_formulas": _feature_formulas(template_style, params),
            "parameter_source_quality": extraction.get("parameter_source_quality", "missing"),
            "parameterization_status": parameterization,
            "missing_for_backtest": [],
            "candidate_export_allowed": not still_hft,
            "backtest_spec_export_allowed": not still_hft,
            "source_reported_metrics": extraction.get("reported_metrics", {}) or {},
            "order_assumptions": (
                "market (taker) orders at next 1m bar open after signal; no partial fills "
                "modeled; execution latency tolerance >= 1 bar (non-HFT by construction)"
            ),
            "baseline_comparisons": [
                "buy-and-hold on the same universe",
                "randomized-entry baseline with identical exits and sizing",
                "unconditional variant (same rules without the regime/filter condition)",
            ],
            "expected_failure_modes": [
                "edge is an artifact of survivorship or lookahead bias",
                "signal decays after fees at the target timeframe",
                "regime dependence: works only in trending/high-vol samples",
            ],
            "minimum_viable_backtest": _build_minimum_viable_backtest(
                asset_universe, robustness_universe, timeframe, data
            ),
            "optimization_parameters": _optimization_grid(params),
            "optimization_constraints": STYLE_CONSTRAINTS.get(template_style, []),
            "walk_forward_validation_plan": (
                "Rolling walk-forward: 12-month train / 3-month test, stepped quarterly; "
                "require positive OOS expectancy in >=60% of folds."
            ),
            "anti_overfitting_checks": [
                "parameter-stability heatmap (edge must not live in one cell)",
                "deflated Sharpe ratio on OOS results",
                "test on assets not used for parameter selection",
            ],
            "priority_score": 0,
            "status": status,
            "hft_or_low_latency_dependency": still_hft,
            "non_applicable_reason": NON_APPLICABLE_HFT if still_hft else "",
            "original_source_has_latency_dependency": source_hft,
            "adapted_to_non_hft": adapted,
            "adaptation_validity": (
                "invalid" if still_hft else "strong" if adapted else "not_needed"
            ),
            "non_hft_adaptation": (
                "signal aggregated to 1m+ bars / quoting slowed to minutes cadence; "
                "edge re-based on inventory/flow information, not reaction speed"
                if adapted else ""
            ),
        }
        # Executable-spec consistency (v0.2.1 P1): validate the assembled
        # payload against its own source facts before returning it.
        from research_intel.hypotheses.spec_consistency import validate_spec_consistency

        payload.update(validate_spec_consistency(payload))
        return payload

    def score_hypothesis(self, hypothesis: dict[str, Any]) -> dict[str, Any]:
        style = hypothesis.get("strategy_style", "generic")
        hft = bool(hypothesis.get("hft_or_low_latency_dependency"))
        data = hypothesis.get("required_data", [])
        easy_data = {"ohlcv", "volume", "funding_rates", "futures_basis", "liquidations",
                     "cross_sectional_universe"}
        hard_data = {"order_book_snapshots", "trades"}
        data_score = 9.0 if all(d in easy_data for d in data) else (
            6.0 if any(d in hard_data for d in data) else 7.0)

        ungrounded = hypothesis.get("parameterization_status") in (
            "default_parameterized", "unparameterized",
        ) or not hypothesis.get("candidate_export_allowed", True)
        clarity = (
            2.0 if ungrounded
            else 8.0 if hypothesis.get("entry_rules") and hypothesis.get("exit_rules") else 3.0
        )
        complexity = {"momentum": 8.0, "mean_reversion": 8.0, "volatility_regime": 7.0,
                      "carry_basis": 7.0, "event_driven": 6.0, "flow_imbalance": 6.0,
                      "cross_sectional": 6.0, "statistical_arbitrage": 5.0,
                      "market_making": 4.0, "portfolio_risk": 7.0}.get(style, 5.0)
        novelty = {"carry_basis": 5.0, "momentum": 4.0, "mean_reversion": 4.0,
                   "event_driven": 7.0, "flow_imbalance": 6.5}.get(style, 5.5)

        evidence = {"explicit": 8.0, "partially_explicit": 6.0, "inferred": 4.0,
                    "missing": 2.0}[hypothesis.get("parameter_source_quality", "missing")]
        if hypothesis.get("source_reported_metrics"):
            evidence = min(10.0, evidence + 1.0)

        dims = {
            "crypto_relevance": 9.0 if hypothesis.get("market") == "crypto" else 5.0,
            "non_hft_compatibility": 0.0 if hft else 9.0,
            "data_availability": data_score,
            "backtest_feasibility": (
                2.0 if ungrounded
                else 8.0 if hypothesis.get("minimum_viable_backtest") else 3.0
            ),
            "signal_clarity": clarity,
            "expected_robustness": 6.0,
            "novelty": novelty,
            "implementation_complexity": complexity,
            "overfitting_risk": 7.0 if hypothesis.get("anti_overfitting_checks") else 3.0,
            "transaction_cost_sensitivity": 4.0 if hypothesis.get("timeframe") == "1m-15m" else 7.0,
            "portfolio_diversification_value": 7.0 if style in (
                "carry_basis", "statistical_arbitrage", "market_making", "portfolio_risk"
            ) else 5.0,
            "expected_edge_decay_risk": 6.0,
            "source_evidence_quality": evidence,
        }
        assert set(dims) == set(SCORING_DIMENSIONS)
        return {
            "hypothesis_id": hypothesis.get("hypothesis_id", ""),
            "dimensions": dims,
            "rationale": {"summary": f"heuristic mock scoring for style={style}, hft={hft}, "
                          f"evidence={evidence}"},
        }
