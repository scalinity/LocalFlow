export const MODE: Record<string, string> = {
  raw: 'As heard',
  clean: 'Clean',
  polish: 'Polish',
  concise: 'Concise',
  prompt_engineer: 'Prompt Engineer',
  custom: 'Custom transform',
};

export const CATEGORY: Record<string, string> = {
  personal_messaging: 'Personal messages',
  work_messaging: 'Work messages',
  messaging: 'Messages',
  email: 'Email',
  documents: 'Documents',
  ai_prompt: 'AI prompts',
  coding: 'Code',
  terminal: 'Terminal',
};

export const NUMBERS: Record<string, string> = {
  inherit: 'Default',
  technical: 'Technical — digits',
  standard: 'Standard — words',
};

export const SCOPE_KIND: Record<string, string> = {
  global: 'Everywhere',
  category: 'A kind of place',
  app: 'One app',
  site: 'One website',
  workspace: 'One workspace',
};

export function where(scope: [string, string | null] | null): string {
  if (!scope || scope[0] === 'global') return 'Everywhere';
  if (scope[0] === 'category') return CATEGORY[scope[1] ?? ''] ?? scope[1] ?? '';
  return scope[1] ?? SCOPE_KIND[scope[0]];
}

export function source(src: string | null | undefined, category?: string | null): string {
  if (!src) return '';
  if (src === 'job_override') return 'the one-time override for the next dictation';
  if (src === 'global_default') return 'LocalFlow’s default';
  if (src === 'category_default') return `the default for ${CATEGORY[category ?? ''] ?? 'this kind of place'}`;
  if (src.startsWith('rule:')) return `your rule for ${src === 'rule:global' ? 'everywhere' : src === 'rule:category' ? CATEGORY[category ?? ''] ?? 'this kind of place' : `this ${src.slice(5)}`}`;
  return src.replace(/_/g, ' ');
}
