export type Choice = 'a' | 'b' | 'tie' | 'both_wrong';
export type Pair = { pair_id: string; case_id: string; source: string; a: {text: string}; b: {text: string}; vocabulary: [string,string][] };
export type Annotation = { pair_id: string; choice: Choice | null; note: string; seconds: number; annotated_at: string };
export type Progress = { total: number; completed: number; counts: Record<Choice, number>; median_seconds: number | null; timings: [string, number][] };
export type Snapshot = { pairs: Pair[]; queue: string[]; drafts: Record<string,string>; progress: Progress; can_undo: boolean };
export interface Backend { load(): Promise<Snapshot>; judge(id: string, choice: Choice, note: string, seconds: number): Promise<Snapshot>; undo(): Promise<Snapshot>; skip(id: string): Promise<Snapshot>; draft(id: string, note: string): Promise<void>; export(): Promise<void> }
