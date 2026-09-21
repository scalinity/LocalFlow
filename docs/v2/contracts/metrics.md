# Contract: Metrics

**Spec/eval:** E06, S21, S24 · **Owner:** M01 · **Suites:** all EV report against these definitions

Definitions live in Evaluation E06; this contract fixes the reporting
discipline every milestone's results must follow.

## Reporting rules

1. Every quantile states cohort size, failure/timeout count, context/mode
   and build. Failed jobs stay in the report; a slower model must not look
   fast because its failures vanished.
2. A null measurement stays `null` with its reason; it never converts to a
   pass or a zero.
3. Stage timings and end-to-end timings are reported separately. The
   legacy-log baseline (176.6 s ASR / 629.6 s cleanup over 477 timed pairs)
   is stage-only on rounded values — never cited as release-to-insert.
4. WPM aggregation is `60 × sum(words) / sum(capture_seconds)`, not an
   average of row WPMs. `fixed_words` stays a legacy label.
5. Change statistics from the legacy corpus (257 changed / 108 lexical /
   133 boundary-adding loaded-cohort pairs — historical figures; the
   machine-derived reconciliation reports 257/107/134 with the ±1 method
   delta explained in `../baseline/legacy-log-reconciliation.json`) are
   triage signals, not error labels.
6. Training readiness metrics (E19.4) are separate from usage analytics;
   an unedited paste is `unlabeled`, not a verified positive.

## Baseline anchors recorded by M01

- Historical stage timings: `docs/v2/baseline/legacy-log-reconciliation.json`
  and the preserved `../EVIDENCE_SUMMARY.json` / `../LATENCY_BASELINE.csv`.
- Current-machine probe: `../benchmarks/<run-id>/` (see handoff for the
  concrete run).
