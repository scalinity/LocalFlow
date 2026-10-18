/**
 * Terms are introduced where the story first needs them. `plain` is what a newcomer needs
 * to keep reading; `technical` is added from the Research depth on.
 */
export interface GlossaryEntry {
  term: string
  plain: string
  technical?: string
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  dictation: {
    term: 'Dictation',
    plain: 'Speaking instead of typing: you talk, and the computer writes down what you said.',
  },
  'speech-recognizer': {
    term: 'Speech recognizer',
    plain: 'The program that turns the sound of your voice into words on the screen. It writes down what it hears, including the “um”s and the mid-sentence changes of mind.',
    technical: 'An automatic speech recognition (ASR) model. LocalFlow uses NVIDIA’s Parakeet family, run on the Mac.',
  },
  transcript: {
    term: 'Transcript',
    plain: 'The raw words the speech recognizer wrote down, before any tidying.',
  },
  cleanup: {
    term: 'Cleanup',
    plain: 'Turning a raw transcript into the text you meant: dropping fillers, applying “no, I mean…” corrections, and fixing punctuation, without changing what you said.',
    technical: 'A constrained rewriting task: allowed edits are deletions of fillers, stutters and corrected spans plus punctuation and casing; content words must be preserved.',
  },
  'self-correction': {
    term: 'Self-correction',
    plain: 'When a speaker changes their mind mid-sentence: “at 8, no, 9 o’clock”. The cleanup should keep only “9 o’clock”.',
    technical: 'Scored by correction_success on cases with gold correction lines: no obsolete value kept and no listed fact missing.',
  },
  'language-model': {
    term: 'Language model',
    plain: 'A program that has read an enormous amount of text and can continue or rewrite text. LocalFlow uses a small one that runs on the Mac itself.',
    technical: 'A decoder-only transformer. The study’s models are Qwen3.5 networks with 4 and 9 billion parameters, quantized to 4 bits for on-device inference.',
  },
  parameters: {
    term: 'Parameters (4B, 9B)',
    plain: 'The adjustable numbers inside a language model. “4B” means about 4 billion of them. More usually means more capable, but also slower and larger.',
  },
  'on-device': {
    term: 'On-device',
    plain: 'Running on your own computer, so your words never leave it and nothing costs money per use.',
  },
  'fine-tuning': {
    term: 'Fine-tuning',
    plain: 'Teaching an existing model a specific job by showing it many worked examples, the way an apprentice learns by watching corrections.',
    technical: 'Supervised training on input-target pairs. Here: LoRA adapters trained on cleanup examples, with the base network frozen.',
  },
  inference: {
    term: 'Running a model',
    plain: 'Using a trained model to produce answers. Nothing is learned while it runs; the model is the same before and after.',
    technical: 'Inference: the local models run through LocalFlow’s production engine on the Mac; the Claude systems through Anthropic’s batch service.',
  },
  untuned: {
    term: 'Untuned model',
    plain: 'A model used as it comes, with only written instructions (a prompt) and no training on the job.',
  },
  prompt: {
    term: 'Prompt',
    plain: 'The written instructions given to a model along with the text to work on.',
  },
  adapter: {
    term: 'Adapter',
    plain: 'A small add-on trained on top of a model, like a clip-on lens: the model underneath stays the same, the adapter changes how it behaves.',
    technical: 'LoRA (low-rank adaptation): small trainable matrices added to selected layers. “Continued from C” starts from C’s adapter; a “fresh” adapter starts from zero on the same base.',
  },
  'training-data': {
    term: 'Training data',
    plain: 'The worked examples a model learns from: each one a messy transcript paired with the cleaned-up text it should produce.',
  },
  'synthetic-data': {
    term: 'Synthetic data',
    plain: 'Examples written to look like real dictation, rather than recorded from real speech. They can be made in large numbers and checked carefully, but they are not real recordings.',
    technical: 'In this study, Claude Sonnet wrote inputs and target cleanups; a deterministic rule engine and validator checked them; Claude Opus reviewed verifications.',
  },
  dataset: {
    term: 'Dataset',
    plain: 'A collection of examples, kept in separate piles for learning, for practice testing and for the final test.',
  },
  'development-set': {
    term: 'Development set',
    plain: 'The practice exam: 431 cases used while building and choosing models. Looking at it many times is allowed, so its results guide decisions but do not prove them.',
  },
  'final-set': {
    term: 'Final set',
    plain: 'The real exam: 955 cases locked away until the plan was sealed, then used once. Only its results can confirm a claim.',
    technical: 'A/refinement/dataset/test.jsonl, bound by the dataset freeze and the seal record; opened once per system after the seal.',
  },
  'answer-key': {
    term: 'Answer key',
    plain: 'For each test case, a written example of the correct cleanup. Graders and the automatic checks compare each model’s answer with it.',
    technical: 'The `target` field of each case, also called the reference.',
  },
  reference: {
    term: 'Reference',
    plain: 'Another word for one entry in the answer key: the example of a correct cleanup for one case.',
  },
  'reference-policy': {
    term: 'Answer-key style',
    plain: 'The rules the answer key was written by. The original key allowed extra commas and paragraph breaks; the newer minimal-edit style removes those, while keeping every word the same.',
    technical: 'Earlier label policy versus the minimal-edit policy implemented by minimal_target in v2/policy_score.py.',
  },
  'minimal-edit': {
    term: 'Minimal-edit style',
    plain: 'Change only what must change: remove fillers, apply corrections, fix punctuation that is wrong, and add nothing the speaker did not say.',
  },
  checkpoint: {
    term: 'Checkpoint',
    plain: 'A saved copy of a model partway through its training. Training saves many; one is chosen to keep.',
    technical: 'Selected by lowest validation loss (the pre-registered rule); “ck426” means the copy saved after 426 training updates.',
  },
  seed: {
    term: 'Seed',
    plain: 'A starting number for the randomness in training. Training the same model with different seeds shows how much results vary by luck.',
  },
  'rule-engine': {
    term: 'Rule engine',
    plain: 'A conventional program, with no AI in it, that checks a cleanup against strict rules: no words added, none dropped except allowed ones, numbers kept.',
    technical: 'The deterministic engine and validator in the LocalFlow cleanup stack; the scorer reuses its checks (lfx/score.py score_synthetic).',
  },
  'engine-damage': {
    term: 'Engine damage',
    plain: 'The rule engine’s alarm for an answer that changed what was dictated: a word added, a needed word dropped, a “not” lost, or the ending cut off.',
    technical: 'damage = facts_missing or hallucination or omission or negation_changed or missing_ending or unwanted_answer (lfx/score.py:168).',
  },
  'no-op': {
    term: 'Text that needs no change',
    plain: 'A test case whose transcript is already correct. The right answer is to return it exactly as it is.',
    technical: 'is_noop cases; noop_preserved requires the output to equal the input byte for byte (253 of the 431 development cases).',
  },
  judge: {
    term: 'AI grader',
    plain: 'A large AI model asked to grade each answer against the answer key with a fixed checklist. Using graders from different companies guards against one company’s taste deciding the result.',
    technical: 'An LLM judge with frozen instructions and a JSON verdict schema (v2/judge.py). Answers to one case are shown together, in a shuffled order, without model names.',
  },
  'judged-pass': {
    term: 'Judged pass',
    plain: 'The grader found nothing wrong with the answer and judged the cleanup complete (or rightly unnecessary).',
    technical: 'No flag among semantic_damage, critical_fact_changed, hallucination, unwanted_edit, and cleanup ∈ {complete, none_needed}; delivered stage only.',
  },
  blind: {
    term: 'Blind grading',
    plain: 'The grader sees the answers without knowing which model wrote which, in a shuffled order.',
  },
  'pre-registration': {
    term: 'Pre-registration',
    plain: 'Writing down the questions, the tests and the pass marks before seeing the results, so nobody can move the goalposts afterwards.',
  },
  seal: {
    term: 'Seal',
    plain: 'The moment the plan was locked: its files were fingerprinted and published, so any later change would show.',
    technical: 'docs/v2/research/seal/FREEZE.json, SHA-256 recorded in seal/FROZEN, at commit 6a40964 (October 17, 4:47 p.m. ET).',
  },
  amendment: {
    term: 'Amendment',
    plain: 'A written change to the plan, made and published before the results it could affect were known.',
  },
  hypothesis: {
    term: 'Hypothesis',
    plain: 'A specific guess the study set out to test, written down in advance (H1 to H5).',
  },
  claim: {
    term: 'Claim',
    plain: 'A statement the final test can confirm or reject, each with a pass mark set in advance (C1 to C5).',
  },
  'confidence-interval': {
    term: 'Confidence interval',
    plain: 'A range that shows how sure we can be. “+3.5 points, between +1.2 and +5.8” means the true difference is very likely somewhere in that range; if the range includes zero, the data cannot rule out no difference.',
    technical: 'Percentile intervals from a paired bootstrap: 10,000 resamples of cases, seed 20261015; 95 percent in Stage 1 (Bonferroni-adjusted for the family), 99 percent in Stage 2.',
  },
  bootstrap: {
    term: 'Bootstrap',
    plain: 'A way to measure uncertainty by re-drawing the test cases many times and seeing how much the result wobbles.',
  },
  'non-inferiority': {
    term: 'Non-inferiority',
    plain: 'Showing a model is “not meaningfully worse”: the whole uncertainty range must stay above a pre-set allowance, such as “no more than 3 points behind”.',
  },
  'percentage-points': {
    term: 'Percentage points',
    plain: 'The plain difference between two percentages: going from 85% to 89% is 4 percentage points.',
  },
  'few-shot': {
    term: 'Few-shot',
    plain: 'Giving a large model a handful of worked examples in its instructions instead of training it.',
  },
  'frontier-model': {
    term: 'Frontier model',
    plain: 'One of the largest, most capable AI models, run in a company’s data centre and paid per use. Here: Claude Sonnet 5.5 and Claude Opus 5.5.',
  },
  'intersection-union': {
    term: 'Both graders must agree',
    plain: 'A judged claim counts only if it passes under each grader separately. Adding a grader can only make a claim harder to pass.',
    technical: 'Intersection-union test: each component holds its own α, so requiring all components needs no further correction.',
  },
  'missing-outcome': {
    term: 'Missing outcome',
    plain: 'A result that does not exist, such as a refused answer. It is never counted as a pass or a fail; instead the claim must hold both without it and with it counted against the claim.',
  },
  latency: {
    term: 'Latency',
    plain: 'How long you wait between finishing speaking and seeing the cleaned text.',
  },
  quantization: {
    term: '4-bit quantization',
    plain: 'Storing the model’s numbers with less precision so it fits in a laptop’s memory and runs faster, at a small cost in accuracy.',
  },
  kappa: {
    term: 'Kappa',
    plain: 'A measure of how much two graders agree beyond what chance alone would produce: 0 is chance, 1 is perfect agreement.',
  },
  'contrast-rows': {
    term: 'Contrast rows',
    plain: 'Training pairs that show the same kind of sentence twice: once where an edit is needed and once where it must be left alone, so the model learns when not to edit.',
  },
  'verifier-filtering': {
    term: 'Verifier filtering',
    plain: 'Throwing out training examples that a checking step rejected, instead of training on them anyway.',
  },
}
