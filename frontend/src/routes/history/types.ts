export interface Row {
  kind: string;
  id: string;
  date: string | null;
  time: string | null;
  app: string | null;
  mode: string | null;
  state: string | null;
  preview: string | null;
  has_audio: boolean;
}

export interface Group {
  label: string;
  rows: Row[];
}

export interface Stage {
  stage: string;
  label: string;
  present: boolean;
  purged: boolean;
  text: string | null;
  reason: string | null;
  decision: { path?: string; reason?: string; applied?: boolean } | null;
}

export interface Detail {
  token: string;
  kind: string;
  job_id: string | null;
  captured_at_utc: string | null;
  time: string | null;
  time_quality: string | null;
  state: string | null;
  state_reason: string | null;
  attempt: number | null;
  lineage_attempt: number | null;
  lineage_ambiguous: boolean;
  app: string | null;
  final_stage: string | null;
  final_text: string | null;
  audio: { available: boolean; reason: string | null };
  insertion: { state: string; method: string; reason_code: string | null } | null;
  lineage: Stage[];
}
