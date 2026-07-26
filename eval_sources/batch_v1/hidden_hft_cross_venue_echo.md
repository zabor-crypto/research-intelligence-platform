# Cross-Venue Price Echo Capture in Crypto Order Flow

Adversarial hidden-HFT source #2. No classic HFT terminology.

## Abstract

Price changes on the leading venue echo on lagging venues within a fraction
of a second. We document a strategy that trades the lagging book in the
direction of the leader's move. The edge disappears if delayed by one second,
and captured profit decays monotonically with reaction time: the system must
be first to refresh quotes after each depth change on the lagging venue, and
must cancel and repost before competitors reprice.

## Results

All of the strategy's return is earned by reacting within the same order-book
update cycle as the leader's price change. A variant that waits for the next
one-minute bar captures nothing: the echo is fully absorbed within roughly
400 milliseconds on liquid pairs.
