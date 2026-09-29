# Cross-milestone remediation — native, manual, model and human qualification ledger

The source-remediation campaign closes with these obligations still open. None is passed or implied passed: each keeps its exact case ids and the later gate or runbook check that owns it. Automated evidence in `remediation/final/` counts only for what it actually exercised.

## GATE-G07 — closed for the source remediation, with remaining native qualification

State: `CLOSED_FOR_CROSS_MILESTONE_SOURCE_REMEDIATION_WITH_REMAINING_NATIVE_QUALIFICATION`.

Automated evidence and what it covers: `final/native_xm_hub.json` — the owned synthetic Hub suite, passive tier, 6/6, never frontmost (transform row fills its instruction and Update keeps it; stale transform editor admission; Export Validate result lifetime; the minimum-width Settings controls; pane switch; window close as exercised there).

Remaining native qualification:

| Obligation | Case ids | Owner |
|---|---|---|
| The Hub's active tier: real keyboard and focus, Insights, Review / A-B, Your Voice, active deletion and revocation in a key window | XM-C196, XM-C121 | GATE-G07 active tier; VERIFICATION.html M09-V001 (larger text, light and dark), M09-V002 (keyboard only); M12 native checks LF-M12-N002/N004/N006 |
| Clipboard survival on the real pasteboard | XM-C197 | `tests/v2/insertion/test_native_insertion.py` native tier; VERIFICATION.html M08-V002 |
| History → Paste Again with a real click: the Hub steps aside, the click lands in a real app's field, the text is pasted there, Esc and the 30-second timeout cancel, and a secure field refuses | POLICY-D03 | native qualification of the picker's NSEvent global monitors and hint panel (the policy is proven on the production path in `test_xm_paste_again.py` with the monitors replaced by the test acting as the user) |
| Retry from the Hub or Recovery menu in the real app keeps its result without inserting | XM-C042 | native qualification (proven on the production path in `test_xm_g06_c2.py`) |

## GATE-G08 — closed for the source remediation, with remaining human / M15 performance qualification

State: `CLOSED_FOR_CROSS_MILESTONE_SOURCE_REMEDIATION_WITH_REMAINING_HUMAN_M15_PERFORMANCE_QUALIFICATION`.

Measured after correctness, on this Mac, and kept as exactly that evidence: the dictation-shaped Store writer wait beside each background job, the Hub's construction, first usable result and full pass, and History search — each with its benchmark's own validity controls (the final benchmark directory named in `adjudications.json` records).

Remaining: the true human-speaker release-to-terminal dictation measurement (p50/p95/p99/max) on the reference Mac. No synthetic-audio figure stands in for it. Cases XM-C191 (DEFERRED_HUMAN), XM-C192, XM-C194, XM-C195, XM-MH32 (DEFERRED_M15); owner M15-AC03/AC04.

## Model qualification

| Obligation | Case / requirement | Owner |
|---|---|---|
| M07 long-prompt cleanup trial | M07-V001; XM-C065 | VERIFICATION.html M07-V001; `tests/v2/fidelity/test_fidelity.py` (model-backed EV-09); M15-AC02 |
| M07 adjudicated real-text stratum | M07-V002 | BLOCKED until the separate private legacy-transcript review tool exists and the 749 candidates are reviewed (a pre-M15 workstream after this remediation reaches `main`) |
| M11 integrated record (one misdirected review, fourteen output-limit fallbacks) | GATE-G10 | M11 local verification |
| ASR language coverage | LF-R27 | M15; EV-17 (M16) |
| A qualified decoder adapter and acoustic strata | LF-R29 | M15 |

## Human and whole-app acceptance

| Obligation | Case / requirement | Owner |
|---|---|---|
| Real microphones and device switching | LF-R04 | VERIFICATION.html M03-V006 |
| Whole-app offline operation observed at runtime | LF-R25 | EV-17 (M16) |
| The runbook's manual checks, all Not run as committed | — | docs/v2/VERIFICATION.html |
| M15 preconditions and acceptance | XM-C187, XM-C188, XM-C189, XM-C190 | M15 |
