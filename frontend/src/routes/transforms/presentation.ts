// Keep these labels aligned with the native review actions. They describe
// review only; tutorial controls never send a replacement to another app.
export const REVIEW_ACTIONS = [
  { id: 'accept', label: 'Accept ↵', meaning: 'Replace the verified selection without submitting it.' },
  { id: 'copy', label: 'Copy', meaning: 'Copy only the finished text.' },
  { id: 'refine', label: 'Refine…', meaning: 'Open the complete result in the prompt workspace for further editing.' },
  { id: 'retry', label: 'Retry Original', meaning: 'Generate again from the original source and frozen context.' },
  { id: 'another', label: 'Apply Another…', meaning: 'Choose another transform for the original source.' },
  { id: 'chain', label: 'Transform Output…', meaning: 'Use this result as the next transform’s source.' },
  { id: 'scratchpad', label: 'Save to Scratchpad', meaning: 'Save the result as a local note.' },
] as const;
export const REVIEW_CLOSE = { label: 'Close', meaning: 'Dismiss the review without changing the source.' };
export function applyNotice(outcome: string): { text: string; tone: 'info' | 'success' | 'warning' | 'unknown'; pending: boolean } {
  if (outcome === 'applied_verified') return { text: 'Prompt applied and verified in the original destination.', tone: 'success', pending: false };
  if (outcome === 'revalidating_original_destination') return { text: 'LocalFlow is revalidating the original app and window before replacement. The prompt remains available to copy.', tone: 'info', pending: true };
  if (outcome === 'apply_already_started' || outcome === 'outcome_unknown') return { text: 'Replacement may already be underway. Check the original destination before trying again. The prompt remains available to copy.', tone: 'unknown', pending: true };
  return { text: `Replacement status: ${outcome.replaceAll('_', ' ')}. The prompt remains available to copy.`, tone: 'warning', pending: false };
}
export const TUTORIAL_ORIGINAL = 'please ask to move the design review to thursday because the draft needs another pass';
export const TUTORIAL_POLISHED = 'Please ask to move the design review to Thursday because the draft needs another pass.';
export const TUTORIAL_PROMPT = 'Draft a message asking to move the design review to Thursday. Explain that the draft needs another pass.';
