# Market Structure Note: Anatomy of Liquidation Cascades

Blog-style market structure commentary.

Liquidation cascades in crypto perps unfold in a recognizable sequence: an
initiating move breaches a cluster of liquidation prices, forced market
orders consume the book, spreads widen, and market makers pull quotes until
the forced flow exhausts. The interesting part for medium-frequency traders
is the aftermath, not the cascade itself: once forced selling stops, price
tends to retrace a meaningful share of the overshoot over the following
hours.

Cascade clustering matters — open interest builds around round-number levels
and prior swing lows, so liquidation heatmaps have predictive value for where
cascades can start. Retracement odds appear better when the cascade is
concentrated on one venue while others lag, and worse when funding was
already deeply negative before the event.

This note is descriptive; it does not provide entry thresholds, holding
periods, or a tested rule set. Liquidation feeds and open-interest data are
available from the major data vendors.
