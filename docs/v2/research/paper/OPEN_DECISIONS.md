# Decisions that belong to the author

Listed with what each costs and what happens if it is left open. A writing session does not resolve these.

## Done

1. **Claude few-shot baselines (H5).** Done. Both ran on the development set (2026-10-17, combined cap $24) and once on the final set after the seal.
   Opus 5.5 few-shot answered 954 of the 955 final cases; the provider refused one (AMENDMENT-2). Their API costs are in the provider ledger, not in `results/`.
3. **Human annotation.** Done: the author judged all 150 blinded pairs and 15 duplicates on 2026-10-17 between 5:03 and 7:03 p.m. EDT (1 h 25 min of active review), after the seal and before any final-set result existed. `annotations.jsonl` has sha256 `dd073affa2c15e31373cc450661523a13a7b0df72f7f2bee39a96f24702ce9cb`; the seal recorded the file empty.
   Agreement with the three development judges and with Sonnet 5.5 (AMENDMENT-2 item 3) is in EVIDENCE_MAP. The packet was built with `--differing-only` (LIMITATIONS 15) and is `A/research/annotation/pairs.jsonl`.
4. **Sealing and the final set.** Done: sealed 2026-10-17 at 4:47 p.m. EDT at commit 6a40964, before any human annotation existed. The record is
   `docs/v2/research/seal/FREEZE.json` (SHA-256 `f4a1ab44…ffa6`, the content of `seal/FROZEN`). The nine systems of Amendment 1 ran once each on the 955 final cases; the analysis is `results/stage2/analysis.json` (FINDINGS, 2026-10-18).
7. **Footprint gate in the winner rule.** Closed: the plan allowed a change only before any judged result, and judged results exist, so the gate stands as written (4-bit weights at most 1.5 times C's size).

## Still open

2. **H2.** The development set has 35 no-change and 27 repair list/question cases, too few for H2, and the final-set claims do not include it. Options: (a) a new set of list and question cases with its own review; (b) report H2 as exploratory, which the paper kit does.
5. **Anthropic's answer.** No formal written authorization has been received; written clarification was requested on 2026-10-21. Until an answer exists: do not release Claude-generated rows, targets or weights, describe aggregates only, and cite the Help Center reply only as informal guidance.
6. **Venue, advisor approval and authorship.** ACL 2027 via ARR (January 5, 2027, 6:59 a.m. ET), Interspeech 2027 (February 9, 2027) and ASLI 2027 (April 22, 2027, 7:59 a.m. ET) are the dated options; an arXiv posting and an ICML workshop are the others. The advisor approves the plan once there is a convincing draft; whether the advisor is a co-author is the author's call. Nothing is submitted or posted before Anthropic answers (item 5).
8. **More seeds.** Seeds 1 and 2 exist only for M1 and M2. The ablation arms and M3 have one seed each; each added seed costs about $3.5 of GPU time.
9. **A policy-neutral evaluation.** The development references follow the earlier label policy (43 percent of repair references differ from the new policy's form), and C3 shows the key's policy moves judged comparisons on the final set too. Options: human preference pairs, a set written under the new policy with more list and question cases, or both. The choice between more complete repairs and restraint is a product decision.
10. **Which model to ship.** The pre-registered rule says keep C; the post-hoc noninferiority reading names M2 (SELECTION.md); the final set did not confirm M2 over C under both graders (C1 passes under gpt-6.1-sol, not under Sonnet). Accepting one is a product decision this kit does not make.
