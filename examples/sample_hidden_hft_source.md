# Adverse Selection Avoidance in Passive Crypto Execution

## Abstract

We describe a passive execution strategy for crypto markets built on
inventory-aware quoting. The strategy quotes both sides of the book and
manages inventory risk. However, profits require reacting within the same
order-book update: the system must cancel and repost before competitors
update quotes, and the edge comes from being first in the book after each
update. In simulation, profitability vanishes when orders are delayed beyond
one tick, and the strategy loses edge if delayed by one second.

## Data

Trade and depth records for BTC perpetual futures across three venues.

## Results

Realized spread capture is positive only for the fastest participant in each
book update cycle. Slower variants of the same quoting logic lose money after
fees, confirming that the mechanism is reaction speed rather than inventory
management.
