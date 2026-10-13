# Report design

The report helps decide whether a quantized cleanup candidate is worth installing.
It is an offline comparison desk: the recommendation, an actual changed dictation,
and measured tradeoffs share the opening view. The report never substitutes
synthetic scores for real-audio quality or model proposals for delivered output.

## Design tokens

Reuse LocalFlow's Quiet Editorial tokens from `frontend/src/styles/tokens.css`:
canvas `#FCFCFB`, paper `#F4F2EE`, text `#1A1A1A`, teal `#195C5D`, lavender
`#8A5AB5`, error `#A63D2F`. The dark appearance uses the corresponding product
neutrals, with accessible lighter teal and lavender for charts.

Use the system sans stack for controls and measurements; the product's Iowan/
New York serif stack for the recommendation and dictated text. Code and exact
commands use the system monospace stack. All type works without font downloads.

## Layout

Left-align a narrow navigation rail and a wider comparison surface. The opening
view places the recommendation beside a real before/after specimen. Subsequent
sections use full-width curves and tables, with explanatory text limited to a
comfortable reading width. At phone width, navigation becomes a horizontal strip
and comparisons stack in a labeled order.

```text
LocalFlow    Decision                         Actual dictation
             Keep C / upgrade D or E          Source | C | candidate
Decision     Why the measured tradeoff wins   Changes compared
Quality      --------------------------------------------------
Scaling      Synthetic | Real audio       Model-only | Delivered
Engine       Comparison table + directly labeled curves
Examples     --------------------------------------------------
Costs        Search + category + outcome filters
Reproduce    Expandable input / reference / A / C / D / E
```

## Brief review

A generic collection of score cards would hide the specific product failure:
punctuation can remain wrong while lexical accuracy looks excellent. The design
therefore opens on actual text and separates punctuation, preservation, and
lexical repair. Figures include denominators, units, and evidence labels. Empty
measurements display “Not run” rather than zeros or decorative placeholder curves.

No external assets, remote requests, decorative gradients, dashboard shadows,
or automatic motion. Charts have text equivalents. Controls have visible focus,
native labels, keyboard support, and honest empty states. Both appearances and
a narrow viewport receive visual inspection before completion.
