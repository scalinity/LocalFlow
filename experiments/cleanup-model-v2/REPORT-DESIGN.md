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

## Fresh comparison extension

Keep the same six colors, offline type stacks, left alignment, and comparison
desk layout. The main view now answers whether source repairs improve the
new weights on a genuinely fresh set: C, the recorded E configuration, and F.
The opening specimen shows one measured fresh example; the engine section
separately explains the known failures used during development. Label those
two roles explicitly so a repaired demonstration cannot stand in for validation.

```text
Decision      Fresh recommendation       Fresh source | C | F
              Earlier 701-example report (retained, separate)
Quality       Same fresh inputs: C | E | F, two output stages
Training      Original training curves and selected weights
Engine        Restriction attachment | identifiers | restoration
Examples      All fresh examples, with raw checks and inspection notes
Reproduce     Frozen inputs, source versions, exact installation / rollback
```

Brief review: a before/after victory page centered only on the two known
failures would answer the wrong question. Use the full fresh comparison for
the recommendation and keep the earlier complete report available as a
separate local file. Retain explicit denominators, raw automated flags, and
limitations of the fresh read-speech recordings. No new visual system or
decorative chart is needed; the change is which evidence the desk compares.

The full runtime table retains all measurements. Because the opening C samples
overlapped another GPU workload, a completed repeat on the predetermined first
30 synthetic cases gets a second compact table in the same section. Label its
selection and limits beside the figures; never replace the full measurements
with a faster subset or present an incomplete repeat as a result.
