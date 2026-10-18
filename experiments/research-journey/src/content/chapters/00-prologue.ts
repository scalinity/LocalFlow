import type { Chapter } from '../../data/types'

export const prologue: Chapter = {
  id: 'prologue',
  question: 'What is this about?',
  title: 'You speak, it writes, it tidies',
  when: { iso: '2026-10-18', precision: 'day' },
  span: 'The product today',
  status: 'done',
  events: [],
  ideas: [
    {
      id: 'what-localflow-does',
      title: 'Two programs, one after the other',
      provenance: 'observed',
      evidence: ['app-config', 'app-stt', 'installed-config', 'cleanup-contract'],
      figures: [{ key: 'example-trace', from: 1 }],
      levels: {
        1: `LocalFlow is a [[dictation]] app for the Mac: you talk, and it types what you said into whatever you are writing.

Two programs do the work, one after the other, both on your own computer. A [[speech-recognizer]] writes down every word it hears, including the “um”s and the changes of mind. Then a small [[language-model]] tidies that [[transcript]] into the text you meant. This whole story is about the second program, the tidier, and how to know whether it is doing its job.`,
        2: `The recognizer, Parakeet, writes exactly what it hears. The cleanup model reads that transcript and proposes a tidied version: fillers out, [[self-correction|self-corrections]] applied (“at 8, no, 9” becomes “at 9”), punctuation fixed.

A strict [[rule-engine]] then checks the proposal. If the model added a word you never said, or dropped one it should have kept, LocalFlow throws the proposal away and types your original words instead. Everything runs [[on-device]]: your words never leave the Mac.`,
        3: `Speech recognition is Parakeet TDT 0.6B v3, run through parakeet-mlx on the Mac’s GPU {ev:app-stt}. Cleanup is a 4-bit language model run through mlx-lm. The repository default is Qwen3-4B-Instruct-2507 {ev:app-config}; this Mac runs the fine-tuned model C instead {ev:installed-config}.

The validator’s rules {ev:cleanup-contract}:
- dictated words survive, in order, unless a rule allows their removal (fillers, stutters, accepted corrections);
- no word may appear more often than in the source;
- numbers, negations, hedges and protected tokens survive.
One failed check rejects the proposal; after a bounded repair attempt the unchanged dictation ships.`,
        4: `- Speech model: \`mlx-community/parakeet-tdt-0.6b-v3\`, set in localflow/config.py line 10 {ev:app-config}; loaded in localflow/stt.py lines 52–57 {ev:app-stt}.
- Cleanup default: \`mlx-community/Qwen3-4B-Instruct-2507-4bit\`, localflow/config.py line 28 {ev:app-config}.
- This Mac: \`"cleanup_model": "local/LocalFlow-Cleanup-Qwen3.5-4B-4bit"\` in the Application Support settings, with a Hugging Face cache link to the local weights {ev:installed-config}.
- Validator checks: docs/v2/contracts/cleanup.md lines 408–436; fallback to the unchanged dictation, lines 474–520 {ev:cleanup-contract}.`,
      },
    },
    {
      id: 'the-question',
      title: 'The question behind everything',
      provenance: 'interpretation',
      evidence: ['prereg', 'amendment-1'],
      levels: {
        1: `The research asks one practical question: can a small model on your own Mac clean up speech as well as it needs to, removing the “um”s and applying your corrections, without ever changing what you meant?

And the harder half: how do you *prove* it, rather than just believe it? Most of this story is about that second half.`,
        2: `Proving it takes three things: models to compare, a fair test, and a trustworthy way to grade the answers. The models come first (chapters 1 to 3). Then the study builds the test and the grading (chapters 4 to 8), locks the plan (chapter 9), and runs the final test once (chapter 10).

Along the way, some assumptions turned out to be wrong, including one about the test’s own answer key. Those turns are part of the story, not footnotes to it.`,
        3: `The study compares cleanup models on synthetic dictation cases, each with a written answer key, and grades every answer two ways: a deterministic check by the rule engine, and AI graders from different companies. Development results on 431 cases shaped five claims; a final set of 955 cases, sealed until the claims were fixed, tested them once {ev:prereg} {ev:amendment-1}.`,
        4: `- Pre-registration (written before training): docs/v2/research/PREREGISTRATION.md {ev:prereg}.
- Confirmatory claims and their tests: docs/v2/research/AMENDMENT-1.md {ev:amendment-1}.
- Everything in this publication is drawn from the repository at the snapshot commit shown at the bottom of the page, plus a few local records that are named but not published.`,
      },
    },
    {
      id: 'how-to-read',
      title: 'How to read this',
      provenance: 'observed',
      evidence: [],
      levels: {
        1: `Every idea here can be read at four depths. **Story** says what happened and why it mattered. **Mechanism** explains how it works. **Research** gives the exact conditions and numbers. **Evidence** shows the records behind it.

Use the dial at the top to set the depth for the whole page, or the four dots beside any idea to go deeper on just that one. Underlined words open a short definition in the margin. You can stop at Story and still follow the whole journey.`,
        2: `Beside each idea, a small tag says how it is known: “From the records” (read directly from a file or log), “From the analysis” (computed by the planned statistics), “Our reading” (an interpretation), “Reasoned, not measured”, or “Still open”.

Results carry status words with a mark, never colour alone: Supported, Not supported, Not evaluable, Pending, Not tested, and Observed (seen in the data, but not a planned test).`,
        3: `“Not supported” is not the same as “false”: it means the planned test did not pass, which can mean no effect, an effect in the other direction, or too little data. Development results are always marked as such; nothing from the practice set is presented as a final result.`,
        4: `Sources marked “public” link to the file on GitHub at the snapshot commit. Sources marked “local” are records on the research machine (ignored artifacts, run logs, user settings): they are named so a reader knows they exist, but they are not published. Real development examples appear only in a local build of this site, because the case text was written by Claude and is not released.`,
      },
    },
  ],
}
