# Adverse Selection Avoidance in Passive Crypto Execution (Working Paper)

Adversarial hidden-HFT source #1. No classic HFT terminology.

## Abstract

We study a passive quoting strategy for BTC perpetuals whose stated edge is
inventory management. Decomposing fills, however, shows that profits require
reacting within the same order-book update: the system must cancel and
repost before competitors update quotes, and realized spread is positive only
for the participant that is first in the book after each depth change.

## Results

The strategy loses edge if delayed by one second, and profitability vanishes
when orders are delayed beyond one tick. Slower replicas of the identical
quoting logic are unprofitable after fees across all three venues studied.
