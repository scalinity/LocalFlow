# Decisions that belong to the author

Listed with what each costs and what happens if it is left open. A writing session does not resolve these.

1. **Claude few-shot baselines (H5).** Decided 2026-10-17: run them. The combined cap is $24, so the gate's worst-case reservation ($23.56) passes;
   the point estimate is $3.70 (Sonnet $1.23, Opus $2.46). Their final-set run comes after the seal and needs its own cap.
   Commands: `experiments/cleanup-model-v2/README.md`, section "Paper baseline harness", steps 3 and 5.
2. **A confirmatory H2 test.** The development set has 35 no-change and 27 repair list/question cases, too few for H2. Options: (a) a new set of list and question cases made after the freeze, with its own review;
   (b) the locked final set if its metadata shows enough such cases (metadata only; do not open it); (c) report H2 as exploratory.
3. **Human annotation.** Done: the author judged all 150 blinded pairs and 15 duplicates on 2026-10-17 between 21:03 and 23:03 UTC (1 h 25 min of active review), after the seal and before any final-set result existed. `annotations.jsonl` has sha256 `dd073affa2c15e31373cc450661523a13a7b0df72f7f2bee39a96f24702ce9cb`; the seal recorded the file empty. Agreement with the judges is in EVIDENCE_MAP.
   Build the packet with `--differing-only` (see LIMITATIONS 15): with the uniform draw about 125 of the 150 pairs would be identical text. The packet is written to `A/research/annotation/pairs.jsonl`, which the annotation app reads by default.
4. **Sealing and the final set.** Decided: sealed 2026-10-17 at 20:47 UTC at commit 6a40964, before any human annotation existed. The record is
   `docs/v2/research/seal/FREEZE.json` (SHA-256 `f4a1ab44…ffa6`, the content of `seal/FROZEN`). The nine systems of Amendment 1 run once each on the 955 final cases.
5. **Anthropic authorization.** No formal written answer exists. Do not release Claude-generated rows, targets or weights, and cite the support reply only as informal guidance.
6. **Which venue and when.** ACL 2027 via ARR (January 5, 2027) and Interspeech 2027 (February 9, 2027) are the dated options; an arXiv posting and an ICML workshop are the others. The advisor approves the plan once there is a convincing draft.
7. **Footprint gate in the winner rule.** The plan excludes a model whose 4-bit weights exceed 1.5 times C's size. That is a product judgment (on-device memory); change it in `ANALYSIS_PLAN.md` before any judged result if the author disagrees.
8. **More seeds.** Seeds 1 and 2 exist only for M1 and M2. The ablation arms and M3 have one seed each; each added seed costs about $3.5 of GPU time.
9. **A policy-neutral evaluation.** The development references follow the earlier label policy (43 percent of repair references differ from the new policy's form), so neither reference set is neutral. Options: human preference pairs (the packet is built), a confirmatory set written under the new policy with more list and question cases, or both. The choice between more complete repairs and restraint is a product decision.
10. **Which model to ship.** The pre-registered rule says keep C; the post-hoc noninferiority reading recommends M2 (SELECTION.md). Accept one, then confirm with the human packet.
