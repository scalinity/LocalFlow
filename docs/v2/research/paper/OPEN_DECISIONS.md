# Decisions that belong to the author

Listed with what each costs and what happens if it is left open. A writing session does not resolve these.

1. **Claude few-shot baselines (H5).** Planned and costed, refused by the combined $6 cap because the cap checks the worst-case reservation:
   point estimate about $3.90 (Sonnet $1.30, Opus $2.60), worst case $23.56. Spending needs a go and a decision on the cap. Without them H5 has no frontier comparator
   and is written as not tested. Commands: `experiments/cleanup-model-v2/README.md`, section "Paper baseline harness", steps 3 and 5.
2. **A confirmatory H2 test.** The development set has 35 no-change and 27 repair list/question cases, too few for H2. Options: (a) a new set of list and question cases made after the freeze, with its own review;
   (b) the locked final set if its metadata shows enough such cases (metadata only; do not open it); (c) report H2 as exploratory.
3. **Human annotation.** 150 blinded pairs plus 15 duplicates; needs the author's time with the annotation app. Without it there is no human check on the judges and the circularity limitation stays open.
   Build the packet with `--differing-only` (see LIMITATIONS 15): with the uniform draw about 125 of the 150 pairs would be identical text. The packet is written to `A/research/annotation/pairs.jsonl`, which the annotation app reads by default.
4. **Sealing and the final set.** The pre-registration is unsealed. Sealing (`tools/prereg_freeze.py --seal`) must come before any use of the locked final set, which is opened once per system.
   The selected model and the baselines are the systems to evaluate there.
5. **Anthropic authorization.** No formal written answer exists. Do not release Claude-generated rows, targets or weights, and cite the support reply only as informal guidance.
6. **Which venue and when.** ACL 2027 via ARR (January 5, 2027) and Interspeech 2027 (February 9, 2027) are the dated options; an arXiv posting and an ICML workshop are the others. The advisor approves the plan once there is a convincing draft.
7. **Footprint gate in the winner rule.** The plan excludes a model whose 4-bit weights exceed 1.5 times C's size. That is a product judgment (on-device memory); change it in `ANALYSIS_PLAN.md` before any judged result if the author disagrees.
8. **More seeds.** Seeds 1 and 2 exist only for M1 and M2. The ablation arms and M3 have one seed each; each added seed costs about $3.5 of GPU time.
