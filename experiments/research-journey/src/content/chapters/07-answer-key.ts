import type { Chapter } from '../../data/types'

export const answerKey: Chapter = {
  id: 'answer-key',
  question: 'Was the answer key fair?',
  title: 'The answer key has a style',
  when: { iso: '2026-10-16T15:37:00Z', precision: 'day' },
  span: 'October 16 to 17, 2026',
  status: 'done',
  events: ['reference-discovery'],
  ideas: [
    {
      id: 'what-an-answer-key-is',
      title: 'What an answer key does',
      provenance: 'observed',
      evidence: ['judge-code', 'score-code'],
      levels: {
        1: `Every test case comes with one example of a correct cleanup: its entry in the [[answer-key]]. The rule engine compares each model’s answer with it, and the AI graders read it alongside the answers.

An answer key is written by someone, in some style. If the style is a matter of taste, a model that writes in a different but equally good style can be marked down.`,
        2: `Each entry is a [[reference]]. The graders are told not to demand exact stylistic matches (“equally valid punctuation is acceptable”), but the reference still anchors their judgement, and the engine’s exact-match measures compare against it character by character.`,
        3: `For synthetic cases, every grader request carries the case’s \`source\` (the transcript), its \`reference\` and whether it needs no change; then each system’s answer under an anonymous id, shuffled per case {ev:judge-code}. The engine’s damage check compares the answer’s *words* with the input and the reference; its exact-match measures compare the whole text {ev:score-code}.`,
        4: `- Grader request: v2/judge.py lines 129–157 {ev:judge-code}.
- Exact-match measures: \`reference_complete\` and \`reference_repair\` compare \`canon(text) == canon(target)\`, with canon trimming and collapsing spaces only; experiments/cleanup-model-v2/v2/score.py lines 41–63.
- Damage ignores punctuation and casing: it compares words after casefolding and normalization (lfx/score.py lines 116–170) {ev:score-code}.`,
      },
    },
    {
      id: 'two-styles',
      title: 'Two styles of answer key',
      provenance: 'observed',
      evidence: ['policy-code', 'normalize-code', 'commit-policy'],
      figures: [{ key: 'answer-key', from: 1 }],
      levels: {
        1: `The practice and final answer keys were written in the earlier style, which tidies generously: it adds commas, splits long dictations into paragraphs, sometimes turns a comma into a colon. The newer [[minimal-edit|minimal-edit]] style removes those extras.

The difference is only ever punctuation and paragraph breaks. Not one word changes. Try it in the explorer below: switch the key and watch what moves, and what stays exactly as it was.`,
        2: `The rewrite is a rule-based tool, not an AI: it takes an answer-key entry and undoes the extras the earlier style added. It never touches the transcript, the models’ answers, or which cases need no change.

So switching keys is nothing like retraining a model or asking it again. The models’ answers are the same text before and after; only the yardstick they are measured against moves.`,
        3: `The rewrite (\`minimal_target\`, applied by research_normalize_dev.py) {ev:policy-code} {ev:normalize-code}:
- an invented paragraph break becomes a space, and the next word returns to lower case unless it is capitalized for itself;
- a comma added after an opening “okay”, “so” or “well” is removed, unless it is the only comma setting off an addressed person;
- any other added comma within a line is removed, unless it sets off an addressed person;
- a colon that replaced a dictated comma in a sentence’s first eight words becomes a comma again.
Words and commas the speaker already had are never touched.`,
        4: `- On the development set: 69 references rewritten, 355 unchanged (all 253 no-change cases among them), 7 excluded because the earlier key had made a numbered list or added words that cannot be safely undone {ev:normalize-code}.
- Development counts per rule: paragraph breaks 84 in 21 cases; opening commas 33 in 29; other added commas 240 in 59; colons 3 in 3.
- The rewrite passes no protected-comma list, so it also strips list and number commas that the training labels keep; whether that was intended is not recorded.`,
      },
    },
    {
      id: 'the-discovery',
      title: 'The discovery: the key leaned one way',
      provenance: 'calculated',
      evidence: ['findings', 'results-rewritten', 'deviations'],
      figures: [{ key: 'categories', from: 1 }, { key: 'key-flip', from: 1 }],
      levels: {
        1: `When the practice results showed the earlier-data models doing as well or better, the team looked at where. The differences sat exactly in the cases where the answer key’s style mattered: long instructions, lists, sentence boundaries.

43 of every 100 repair cases in the practice key were written differently from how the new style would write them. Re-grade against a rewritten key, and the earlier data’s advantage disappears.`,
        2: `The earlier-data models were taught by examples in the earlier style, the same style as the answer key. The new-data models were taught to restrain themselves. Graded against a key that rewards the earlier habits, restraint looks like an incomplete cleanup.

Which style is *right* is a product decision, not a statistical one. What the study can do is measure how much the key’s style moves the comparison.`,
        3: `76 of the 178 repair references (43%) differ from the minimal-edit form: 69 can be normalized, 7 are excluded {ev:findings}. Re-referenced and re-judged by Opus (post hoc), M2 − A2prime goes from −1.2 to +1.8 points and M1 − A2 from −2.4 to +0.5; neither is supported. Pass rates on the rewritten key: C 88.6%, A2prime 91.9%, A2 93.0%, M1 93.6%, M2 93.7% {ev:results-rewritten}.`,
        4: `- Changes concentrate in long instructions (23 of 24 repair cases changed or excluded), list structure (13 of 18), phrase boundaries (16 of 24), boundary questions (6 of 9) and restriction scope (10 of 26).
- The rewritten-key pass was a post-hoc analysis, recorded as a deviation {ev:deviations}.
- Engine exact repairs on the rewritten key: M2 66.3%, M1 64.2% against A2prime 48.9%, A2 46.1% (on the original key 46.4%, 45.3% against 50.0%, 48.9%).`,
      },
    },
    {
      id: 'what-c3-is',
      title: 'C3: does the key’s style move the comparison?',
      provenance: 'observed',
      evidence: ['amendment-1', 'amendment-1-known', 'analysis-code'],
      figures: [{ key: 'shift-calc', from: 2 }, { key: 'claims', from: 3 }],
      levels: {
        1: `C3 is the third of the five claims the final test checked. It is not a model: “C” is the installed model, while C1 to C5 are the final test’s five claims.

C3 asks: if the answer key is rewritten in the new style, does the comparison between new-data and earlier-data models move toward the new data? Practice results said yes, and so did the final set, under both graders.`,
        2: `For each case, C3 measures how much the gap between a new-data model and its earlier-data twin changes when the key changes. Two pairs share the work: M2 against A2prime, and M1 against A2. If the average change is reliably above zero under both graders, C3 is supported.

Only C3 uses the rewritten key. Every other claim uses the original key, the one written down in the plan before the rewrite existed.`,
        3: `Per case, with p the judged pass under the original key and p′ under the rewritten key {ev:amendment-1}:

shift = ((p′M2 − p′A2prime) − (pM2 − pA2prime) + (p′M1 − p′A2) − (pM1 − pA2)) / 2

The mean shift over all cases must have the lower end of its 99% interval above 0, under Sonnet and under gpt-6.1-sol. Development evidence: gpt-6.1-sol +1.97 points (99% interval +0.35 to +4.06), Opus +3.13 {ev:amendment-1-known}.`,
        4: `- Amendment 1, claims table line 88 and “The rewritten key for C3”, lines 122–135 {ev:amendment-1}.
- Code: \`shift()\` and \`stage2_components\` in tools/research_analysis.py lines 291–316; the \`--rewritten-judge\` handling lines 394–405 {ev:analysis-code}.
- On the 69 changed development cases, every verdict that changed moved from fail to pass; neither grader moved any of the four systems from pass to fail {ev:dev-rewritten-verdicts}.`,
      },
    },
    {
      id: 'what-gets-regraded',
      title: 'What changes, and what is reused',
      provenance: 'observed',
      evidence: ['amendment-1', 'analysis-code', 'stage2-logs'],
      figures: [{ key: 'regrade-grid', from: 1 }],
      levels: {
        1: `When the key changes, nothing about the models changes: same transcripts, same answers. Only the cases whose answer-key entry actually changed need fresh grading, so only those go back to the graders.

On the final set, 168 of the 955 entries changed. The other 787 keep the verdicts they already got.`,
        2: `For an unchanged case, the grader would see exactly the same request again (same transcript, same key, same answers), so its existing verdict is reused, and that case adds exactly zero to C3. Re-grading the changed cases uses all nine systems’ answers, so each case is judged in the same company as before.

The engine’s damage check does not change at all: it compares words, and the rewrite changes no words.`,
        3: `Procedure (Amendment 1): the final references are rewritten once, after the seal; only changed cases are re-judged, by both final graders, with the full nine-system roster; unchanged cases keep their main-pass verdicts; the rewritten key serves C3 only {ev:amendment-1}. On October 17 at 10:49 p.m. ET the rewrite changed 168 final references; both graders finished re-grading them by 10:59 p.m. {ev:stage2-logs}.`,
        4: `- 168 cases × 9 systems × 2 stages = 3,024 graded slots, 1,058 distinct answers; every distinct answer graded by both graders {ev:stage2-logs}.
- Reuse rule in code: if a (case, system) pair is in the rewritten verdict file, its verdict is used; if the case is there but the system is not, the value stays missing; otherwise the main pass’s verdict is copied {ev:analysis-code}.`,
      },
    },
  ],
}
