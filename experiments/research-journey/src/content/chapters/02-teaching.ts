import type { Chapter } from '../../data/types'

export const teaching: Chapter = {
  id: 'teaching',
  question: 'Can a small model be taught the job?',
  title: 'Teaching the model: C',
  when: { iso: '2026-10-12', precision: 'day' },
  span: 'October 11 to 12, 2026',
  status: 'done',
  events: ['first-experiment', 'install-c'],
  ideas: [
    {
      id: 'what-teaching-means',
      title: 'What teaching a model means',
      provenance: 'observed',
      evidence: ['readme-cleanup', 'v1-config'],
      levels: {
        1: `[[fine-tuning|Fine-tuning]] means showing a model thousands of worked examples (a messy transcript, and the cleanup it should produce) until it picks up the pattern. It is closer to an apprenticeship than to rewriting the rules.

The model underneath stays the same. It gains a small learned add-on that changes how it behaves on this one job.`,
        2: `Each worked example is one piece of [[training-data]]. During training the model guesses the cleanup, the guess is compared with the example’s answer, and its numbers are nudged to make the right answer a little more likely. Repeat that a few thousand times.

The add-on is an [[adapter]]: a small set of extra trainable numbers clipped onto the frozen network. Training saves snapshots along the way, called [[checkpoint|checkpoints]], and one is chosen to keep.`,
        3: `C’s recipe {ev:v1-config}: a LoRA adapter of rank 16 (scale 2.0) on all 32 layers of Qwen3.5-4B, one pass over 6,393 examples in 803 updates, with the loss computed on response tokens only. It trained in 72 minutes on an M5 Pro laptop; validation loss fell from 0.078 to 0.006 {ev:readme-cleanup}.

The checkpoint was chosen *preservation first*: fewest meaning changes, then the most untouched clean inputs, then repair success. Loss alone never decided.`,
        4: `- Settings: experiments/cleanup-model/config.yaml lines 65–80 {ev:v1-config}.
- Base: \`Qwen/Qwen3.5-4B\` in bf16. It is a hybrid network (24 of 32 layers use Gated DeltaNet linear attention), whose stock training path ran at days per epoch. A chunked gated-delta implementation and prefix-cached training made it practical, about 6 times faster {ev:readme-cleanup}.
- Export: adapter fused into the base and quantized to 4-bit with the same recipe as the untuned Qwen3.5, then checked: same top token at 100% of positions.`,
      },
    },
    {
      id: 'where-examples-came-from',
      title: 'Where the worked examples came from',
      provenance: 'observed',
      evidence: ['readme-cleanup'],
      levels: {
        1: `Nobody hand-wrote six thousand examples. Claude Sonnet, a large AI model, wrote them, and LocalFlow’s own engine checked every one: an example was kept only if the real product would have produced exactly that cleanup.

So the model learned only from answers the product would actually ship.`,
        2: `This is [[synthetic-data]]: examples written to look like dictation rather than recorded from real speech. Each “family” held a clean sentence, its critical facts, a noisy speech-recognizer version, its corrections and the changes allowed. About 30% were already clean and had to come back unchanged, which teaches the model when *not* to edit.

The engine replayed each example and kept it only if the result matched byte for byte.`,
        3: `Kept: 5,238 main-pass and 1,155 corrections-pass training examples (6,393), plus 466 test and 400 validation pairs. The gates rejected about 2,000 candidates, mostly because the engine’s correction parser would not accept the gold deletion (458) or the validator rejected the gold (442). Splits were assigned per family before generation, and near-duplicates were removed across splits {ev:readme-cleanup}.`,
        4: `- Generation: Claude Sonnet 5.5 through the Message Batches API, structured JSON, with LocalFlow’s contract text embedded verbatim in the prompt.
- Spend: $16.21 of a $20 cap, enforced by a ledger that refuses any batch whose worst case would pass $19.50.
- Source: README.md lines 116–137 {ev:readme-cleanup}.`,
      },
    },
    {
      id: 'three-models',
      title: 'Three models, one frozen test',
      provenance: 'calculated',
      evidence: ['readme-results', 'v1-report'],
      levels: {
        1: `The first experiment put three models through the same test: A (the original), B (the newer Qwen3.5 as it comes) and C (Qwen3.5, taught).

The taught model was in a different league. Of every 100 spoken corrections, C handled 96, A handled about 15, and B about 12. C almost never changed what was meant.`,
        2: `The test was frozen before any model produced an answer, so nobody could adjust it after seeing results. It mixed synthetic cases with real recorded speech, transcribed by LocalFlow’s own Parakeet path, and with LocalFlow’s hand-written test sentences.

It also kept the model’s raw output separate from what LocalFlow delivers, because the referee’s fallback can hide a model’s mistakes.`,
        3: `1,086 cases: 466 synthetic, 250 DisfluencySpeech recordings (conversational), 250 FLEURS recordings (read speech), 80 LocalFlow fidelity fixtures and 40 long dictations, frozen at 9:05 p.m. ET on October 11 {ev:readme-results}.

- Needed repairs delivered correctly (297 cases): A 63.6%, B 53.2%, C 98.3%.
- Self-corrections resolved (76): 14.5%, 11.8%, 96.1%.
- Already-clean input left untouched (169): 57.4%, 52.7%, 97.6%.
- Raw output that changed meaning (466): 8.4%, 15.0%, 0.4%.
- Blinded judge, meaning preserved (240): 90.0%, 82.9%, 99.2%.`,
        4: `- Word error rate on conversational audio: 5.08%, 5.89%, 4.05%; on read audio: 6.48%, 6.50%, 6.41%.
- Median warm cleanup: 1.48 s, 1.63 s, 1.62 s. Size on disk: 2.26 GB, 3.03 GB, 2.37 GB.
- Fixtures passed, delivered (80): 97.5%, 96.3%, 97.5%.
- README.md lines 173–186 {ev:readme-results}; the report page {ev:v1-report}.`,
      },
    },
    {
      id: 'consider-c',
      title: 'Why only “consider C”',
      provenance: 'observed',
      evidence: ['readme-outcome', 'installed-config'],
      levels: {
        1: `C passed every check, yet the rules allowed only “consider it”, never an automatic switch. C had learned from the same writer, Claude, that wrote most of the test, so a high score there could partly be familiarity.

That is why the rules also demanded real recordings and LocalFlow’s own test sentences, which Claude never wrote. C held up on those too, and it became this Mac’s cleanup model.`,
        2: `When a model is taught and tested on material from the same source, a good score can mean “learned the job” or “learned the source’s habits”. Independent material is the check. Two public speech collections and LocalFlow’s own fixtures provided it.

Real limits remained, stated in the report: C is hands-off with real transcripts, leaving 45% of conversational ones unchanged, and none of the recordings were the owner’s voice.`,
        3: `C met all ten frozen checks: meaning preserved against A on the synthetic, real-audio and fixture slices; a delivered-repair gain whose 95% lower bound is +29 points; and speed within 1.25 times A’s at the 95th percentile. B failed seven of the ten {ev:readme-outcome}.

On this Mac, the user settings were switched to C around 4:25 a.m. ET on October 12 (from file times) {ev:installed-config}. The repository default stays A, because C’s weights are not published.`,
        4: `- Outcome and limits: README.md lines 188–196 {ev:readme-outcome}.
- C’s identity: \`local/LocalFlow-Cleanup-Qwen3.5-4B-4bit\`, checkpoint 642, 2.37 GB.
- First token about 0.17 s slower than A.
- No written rationale for the switch survives beyond the report’s “consider C”.`,
      },
    },
  ],
}
