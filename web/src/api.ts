// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// The Studio API (/api/studio, OpenAPI at /api/studio/openapi.json). Types mirror the server's
// response models; every response carries provenance.

export interface Prov {
  field: string;
  source_file: string;
  line_or_key: number | string | null;
}

export interface WithProv {
  provenance: Prov[];
}

export interface Chip {
  id: string;
  modality: string;
  state: "modelled" | "described" | "empty";
  data: "available" | "synthetic" | "none";
  recordings: number;
  step: number;
  steps: number;
  profiles: string[];
  values: number;
  sources: number;
  open_questions: number;
  complete: boolean;
}

export interface Card {
  clade: string;
  latin: string | null;
  rank: string | null;
  names: string[];
  representative: { name: string; common_name?: string }[];
  niche: string | null;
  review_status: string | null;
  data: string;
  step: number | null;
  steps: number | null;
  senses: Chip[];
}

export interface Species extends WithProv {
  cards: Card[];
  engine: string;
  modalities: string[];
  totals: { clades: number; senses: number; modelled: number; described: number; empty: number; values: number; references: number; open_questions: number };
}

export interface Knob {
  name: string;
  circuit: string;
  unit: string;
  default: number | boolean;
  range: [number, number];
  kind: string;
  source: string;
  doc: string;
  species_values: { profile: string; value: unknown; source_file: string; line: number | string }[];
}

export interface Citation {
  id: string;
  found: boolean;
  reference?: string;
  authors?: string | null;
  year?: string | null;
  title?: string | null;
  link?: string | null;
  checked?: string;
}

export interface QuantityRow {
  path: string;
  slot: string;
  description: string | null;
  value: number | number[] | string;
  unit: string;
  confidence: string;
  species: string | null;
  conditions: string | null;
  notes: string | null;
  citations: Citation[];
  verification: { tabled: boolean; status: string; quote: string | null };
  consumers: { profile: string; section: string; field: string; rule: string }[];
}

export interface Sources extends WithProv {
  clade: string;
  sense: string;
  sense_info: { organ?: string; signal?: string; modality?: string; notes?: string; citations: Citation[] };
  review_status: string | null;
  quantities: QuantityRow[];
  table: { present: boolean; file: string; verified: number; total: number };
  open_questions: { text: string; scope: string }[];
  requests: { id: string; question: string; status: string; priority: string | null; target: string; kind: string }[];
}

export interface SpecField {
  section: string;
  field: string;
  where: string;
  kind: "rule" | "literal";
  rule?: string;
  text?: string;
  rationale?: string;
  output?: string;
  literal?: unknown;
  value?: number | null;
  value_error?: string;
  library_paths?: Record<string, string>;
  sensor_paths?: Record<string, string>;
  reads_this_sense?: boolean;
}

export interface Model extends WithProv {
  clade: string;
  sense: string;
  engine: string;
  engine_error: string | null;
  circuits: { installed: boolean; ok: boolean; error: string | null; groups: { prefix: string; name: string; count: number }[]; knobs: Knob[]; species_set: number };
  profiles: { name: string; description: string | null; spec_hash: string | null; source_file: string; control: boolean; bundles: number[] | null; fields: SpecField[] }[];
  controls: string[];
  rulebook: { present: boolean; rules: { id: string; status: string; sets: string; species: string; reads: string[]; source_file: string; line: number }[] };
  world_prior: { ok: boolean; error: string | null; library: string; params: { name: string; value: number; kind: string; source: string; reads_this_sense: boolean; reads_this_clade: boolean }[] };
  learned: { path: string; ok: boolean; error: string | null; model_id: string | null; params_total: number | null; param_counts: Record<string, number>; tokenizer: unknown; training_data: unknown; step: number | null }[];
  reflex: { profile: string; source_file: string; fields: SpecField[] }[];
}

export interface Step {
  n: number;
  id: string;
  name: string;
  done: boolean;
  at: string | null;
  detail: string;
  source_file: string | null;
  counts?: { verified: number; total: number };
}

export interface Pipeline extends WithProv {
  clade: string;
  sense: string;
  steps: Step[];
  at: number;
  total: number;
  complete: boolean;
  species: string[];
  steps_file: string;
  clock: { since: string | null; days: number | null; partial: boolean; out_of_order: boolean };
}

export interface UseCases extends WithProv {
  items: { file: string; niche: string; status: string | null; species: string[]; evidence: string[]; template: boolean; html: string }[];
  step: number;
  steps: number;
  template_file: string;
}

export interface Source {
  id: string;
  dataset: string;
  name: string;
  synthetic: boolean;
  streams?: string[];
  labelled: boolean;
  available: boolean;
  reason: string;
}

export interface Arm {
  id: string;
  profile: string;
  world: string;
  role: "species" | "control" | "learned";
  description: string | null;
  bench_arm: string | null;
  available: boolean;
  reason: string;
}

export interface RunOptions extends WithProv {
  modality: string;
  view: string | null;
  sources: Source[];
  arms: Arm[];
  prereg: { file: string; id: string; hash: string; clips: string[]; frozen_at: string; verdict: string | null; verdict_file: string | null }[];
  bench: { found: boolean; error: string | null; features: Record<string, boolean> };
  prior_library: string;
}

export interface Job {
  id: string;
  clade: string;
  sense: string;
  status: string;
  source: Source;
  arms: Arm[];
  seconds: number;
  synthetic: boolean;
  preregistered: boolean;
  created: string;
  ended: string | null;
  error: string | null;
  headline: string | null;
  summaries: Record<string, unknown>[];
}

export interface Health extends WithProv {
  ok: boolean;
  repos: Record<string, { path: string; found: boolean; sha: string | null }>;
  engine: string;
  engine_error: string | null;
  circuits: boolean;
  research: { configured: boolean; url: string | null; token: boolean };
  bench: { found: boolean; error: string | null; features: Record<string, boolean> };
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(await errorText(r));
  return (await r.json()) as T;
}

async function errorText(r: Response): Promise<string> {
  try {
    const j = (await r.json()) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    return JSON.stringify(j.detail ?? j);
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

const base = (clade: string, sense: string) => `/api/studio/${encodeURIComponent(clade)}/${encodeURIComponent(sense)}`;

export const api = {
  species: () => get<Species>("/api/studio/species"),
  health: () => get<Health>("/api/studio/health"),
  sources: (c: string, s: string) => get<Sources>(`${base(c, s)}/sources`),
  model: (c: string, s: string) => get<Model>(`${base(c, s)}/model`),
  pipeline: (c: string, s: string) => get<Pipeline>(`${base(c, s)}/pipeline`),
  useCases: (c: string, s: string) => get<UseCases>(`${base(c, s)}/use-cases`),
  runOptions: (c: string, s: string) => get<RunOptions>(`${base(c, s)}/run/options`),
  jobs: (c: string, s: string) => get<Job[]>(`/api/studio/jobs?clade=${encodeURIComponent(c)}&sense=${encodeURIComponent(s)}&limit=10`),
  job: (id: string) => get<Job>(`/api/studio/jobs/${encodeURIComponent(id)}`),
  eventsUrl: (id: string) => `/api/studio/jobs/${encodeURIComponent(id)}/events`,
  fileUrl: (id: string, path: string) => `/api/studio/jobs/${encodeURIComponent(id)}/files/${path.split("/").map(encodeURIComponent).join("/")}`,
  async run(c: string, s: string, body: { source: string; arms: string[]; seconds: number }): Promise<Job> {
    const r = await fetch(`${base(c, s)}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await errorText(r));
    return (await r.json()) as Job;
  },
  async cancel(id: string): Promise<Job> {
    const r = await fetch(`/api/studio/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
    if (!r.ok) throw new Error(await errorText(r));
    return (await r.json()) as Job;
  },
};
