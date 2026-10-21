// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// The research service's API, reached through Studio's proxy (/api/studio/research →
// RESEARCH_URL/api/research). research is the source of truth for these shapes: its
// docs/API.md lists every route and chat event, and /api/studio/research/openapi.json is the
// schema. Studio's proxy adds the signed-in name and the shared token; the browser never sends
// either.

export const RESEARCH = "/api/studio/research";

// ---------------------------------------------------------------- shapes (research docs/API.md)

export interface Refs {
  claim_id?: string;
  impact_id?: string;
  experiment_id?: string;
  source_id?: string;
  doi?: string;
  section?: string;
  text?: string;
  context_before?: string;
  context_after?: string;
  pending_action_id?: string;
}

export interface CardRow { label: string; before: string; after: string }
export interface ActionPayload {
  id: string;
  kind: string;
  status: string;
  card: { title?: string; summary?: string; rows?: CardRow[]; quote?: string | null; diff?: string; note?: string };
  error?: string | null;
  result?: Record<string, unknown>;
}

export interface TranscriptItem {
  kind: string; // user | assistant | note | thinking | tool | tool_result | card
  text?: string;
  id?: string;
  name?: string;
  label?: string;
  ok?: boolean;
  refs?: Refs;
  action?: ActionPayload;
}

export interface LeastVerified {
  claim_id: string;
  library_path: string;
  value: string;
  status: string;
  why: string;
  species: string | null;
  read_by: string[];
}
export interface OpenQuestion { hypothesis_id: string; statement: string; priority: string; target: string | null; read_by: string[] }
export interface Start { open_questions: OpenQuestion[]; least_verified: LeastVerified[] }

export interface SourceInfo {
  source_id: string;
  title: string;
  authors: string;
  year: number | null;
  venue: string;
  doi: string | null;
  link: string | null;
  full_text: boolean;
  checked: string | null;
}
export interface Passage { passage_id: string; section: string; quote: string; before: string; after: string; source: SourceInfo }
export interface HistoryRow { revision: number; at: string; by: string; summary: string; reason: string }
export interface ClaimCard {
  value: string;
  history: HistoryRow[];
  sources: SourceInfo[];
  passage: Passage | null;
  claim: {
    id: string;
    library_path: string;
    status: string;
    species: string | null;
    conditions: string | null;
    method: string | null;
    mapping: string | null;
    library_notes: string | null;
    notes_by_reviewer: string;
    unverified_reason: string | null;
    revision: number;
  };
}

export interface Impact {
  id: string;
  library_path: string;
  consumers: string[];
  sentences: string[];
  field_summaries: { sentence: string }[];
  profile_rows: { profile: string; section: string; field: string; point: string; old: number | string | null; new: number | string | null; delta_pct: number | null }[];
  world_available: boolean;
  world_reached: boolean;
  world_note: string;
  reflex_rows: { arm: string; theta_old: number; theta_new: number }[];
}

export interface Comparison {
  arm: string;
  objects: number | null;
  judged: boolean;
  verdict: string;
  baseline_hit_rate: number | null;
  baseline_chance_hit_rate: number | null;
  patched_hit_rate: number | null;
  patched_chance_hit_rate: number | null;
  baseline_median_delay_s: number | null;
  patched_median_delay_s: number | null;
  baseline_fires_per_h: number | null;
  patched_fires_per_h: number | null;
}
export interface ExperimentView {
  experiment: { id: string; status: string; sequences: string[]; arms: string[]; error: string | null; profiles_sha: string; bench_sha: string; world_sha: string };
  comparison: Comparison[];
  runlogs: string[];
  progress: { frac?: number; message?: string } | null;
}

export interface KeyVar { name: string; aliases: string[]; secret: boolean; set: boolean }
export interface Service {
  id: string;
  name: string;
  group: string;
  purpose: string;
  need: "required" | "recommended" | "optional" | "none";
  without: string;
  get_key: string;
  state: "set" | "partial" | "not_set" | "no_key";
  vars: KeyVar[];
  checkable: boolean;
}
export interface CandidateClaim {
  claim_id: string;
  library_path: string;
  value: string;
  status: string;
  species: string | null;
  conditions: string | null;
  method: string | null;
  sources: SourceInfo[];
  passage: Passage | null;
}
export interface CandidateDetail { id: string; claims: CandidateClaim[]; mechanism: string }

export interface SettingsPage { groups: string[]; integrations: Service[]; where: string }
export interface KeyCheck { id: string; ok: boolean; detail: string; cached: boolean }

export interface ResearchHealth {
  status: string;
  version: string;
  model: string;
  model_reachable: boolean;
  model_detail: string;
  profiles_sha: string | null;
  github: boolean;
}

// ---------------------------------------------------------------- calls

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${RESEARCH}/${path}`, init);
  if (!r.ok) throw new Error(await problem(r));
  return (await r.json()) as T;
}

async function problem(r: Response): Promise<string> {
  try {
    const j = (await r.json()) as { detail?: unknown };
    return typeof j.detail === "string" ? j.detail : `${r.status}`;
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});
const q = encodeURIComponent;

export const research = {
  health: () => call<ResearchHealth>("health"),
  start: () => call<Start>("start"),
  newConversation: () => call<{ id: string }>("conversations", post({})),
  conversation: (id: string) => call<{ id: string; items: TranscriptItem[] }>(`conversations/${q(id)}`),
  claim: (id: string) => call<ClaimCard>(`claims/${id.split("/").map(q).join("/")}`),
  impact: (id: string) => call<Impact>(`impact/${q(id)}`),
  experiment: (id: string) => call<ExperimentView>(`experiments/${q(id)}`),
  settings: () => call<SettingsPage>("settings"),
  /** One circuit candidate with its claims and passages (Design tab). */
  candidate: (id: string) => call<CandidateDetail>(`circuit-candidates/${q(id)}`),
  /** Re-score every claim (research runs senseai-circuits assess). */
  refreshCandidates: () => call<{ stored: number; skipped: number; circuits: string }>("circuit-candidates/refresh", post({})),
  checkKey: (id: string) => call<KeyCheck>(`settings/${q(id)}/check`, post()),
  decide: (actionId: string, decision: "approve" | "reject", rationale: string) =>
    call<{ message: string; action: ActionPayload }>(`actions/${q(actionId)}/${decision}`, post({ rationale })),
  /** Send a message; yields each Server-Sent Event of the reply as it arrives. */
  async *send(conversation: string, text: string, focus: Record<string, string> | null): AsyncGenerator<{ event: string; data: string }> {
    const r = await fetch(`${RESEARCH}/conversations/${q(conversation)}/messages`, post({ text, focus }));
    if (!r.ok || !r.body) throw new Error(await problem(r));
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parsed = parseSse(buf);
      buf = parsed.rest;
      yield* parsed.events;
    }
  },
};

/** Split a Server-Sent Events buffer into complete events and the unfinished rest. */
export function parseSse(buf: string): { events: { event: string; data: string }[]; rest: string } {
  const blocks = buf.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events: { event: string; data: string }[] = [];
  for (const b of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of b.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length || event !== "message") events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}
