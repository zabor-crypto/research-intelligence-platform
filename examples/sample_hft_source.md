# Queue-Position Alpha in High-Frequency Market Making

## Abstract

We document a profitable high-frequency market making strategy whose edge
derives from maintaining favorable queue position at the top of the order
book. Profitability depends on microsecond reaction to order book updates,
co-location with the exchange matching engine, and latency arbitrage across
venues. The strategy uses FPGA-accelerated tick-to-trade pipelines to win
quote races against competing market makers.

## Mechanism

Expected profit per fill is positive only when our quote sits ahead of
competitors in the queue. Simulations show the edge disappears entirely when
reaction latency exceeds 500 microseconds, confirming the strategy is a pure
speed competition.
