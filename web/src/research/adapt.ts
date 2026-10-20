// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Adapters: research's payloads (its docs/API.md) → what Studio renders. Pure functions, no DOM,
// so they are unit-tested against research's exact shapes. When research changes a payload,
// these and their tests are the one place Studio changes.

import type { ActionPayload, CardRow, LeastVerified, OpenQuestion, Refs, Start, TranscriptItem } from "./client.ts";

export interface ActionCard {
  id: string;
  kind: string;
  status: string;
  title: string;
  summary: string;
  rows: CardRow[];
  quote: string | null;
  note: string;
  error: string | null;
}

export type ChatEvent =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "tool"; id: string; label: string; toolKind: string }
  | { kind: "tool_done"; id: string; ok: boolean; summary: string; refs: Refs }
  | { kind: "card"; card: ActionCard }
  | { kind: "progress"; frac: number | null; message: string }
  | { kind: "error"; message: string; code: string | null }
  | { kind: "done"; stop: string; pending: string[] }
  | { kind: "ignored"; name: string };

const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : v === undefined || v === null ? fallback : String(v));

/** A pending action, from research's ``{"action": {...}}`` event or the action itself. */
export function actionCard(raw: unknown): ActionCard {
  const r = (raw ?? {}) as Record<string, unknown>;
  const a = ((r.action as ActionPayload | undefined) ?? (r as unknown as ActionPayload)) as Partial<ActionPayload>;
  const card = a.card ?? {};
  return {
    id: str(a.id),
    kind: str(a.kind),
    status: str(a.status, "pending"),
    title: str(card.title, "Proposed change"),
    summary: str(card.summary),
    rows: Array.isArray(card.rows) ? card.rows.map((x) => ({ label: str(x.label), before: str(x.before), after: str(x.after) })) : [],
    quote: card.quote ? str(card.quote) : null,
    note: str(card.note),
    error: a.error ? str(a.error) : null,
  };
}

/** One chat event (name + JSON data line) → what to render. Unknown events are ignored. */
export function chatEvent(name: string, data: string): ChatEvent {
  let d: Record<string, unknown> = {};
  try {
    d = (JSON.parse(data) ?? {}) as Record<string, unknown>;
  } catch {
    d = { text: data };
  }
  switch (name) {
    case "text_delta":
      return { kind: "text", text: str(d.text) };
    case "thinking_summary":
      return { kind: "thinking", text: str(d.text) };
    case "tool_call":
      return { kind: "tool", id: str(d.id), label: str(d.label ?? d.name, "Working"), toolKind: str(d.kind) };
    case "tool_result_summary":
      return { kind: "tool_done", id: str(d.id), ok: d.ok !== false, summary: str(d.summary), refs: (d.refs as Refs | undefined) ?? {} };
    case "pending_action":
      return { kind: "card", card: actionCard(d) };
    case "job_progress":
      return { kind: "progress", frac: typeof d.frac === "number" ? d.frac : null, message: str(d.message) };
    case "error":
      return { kind: "error", message: str(d.message, "Something went wrong."), code: d.code ? str(d.code) : null };
    case "done":
      return { kind: "done", stop: str(d.stop), pending: Array.isArray(d.pending) ? d.pending.map((x) => str(x)) : [] };
    default:
      return { kind: "ignored", name };
  }
}

/** A stored transcript item (``GET conversations/{id}``) → the same events a live turn makes. */
export function transcriptEvents(items: TranscriptItem[]): (ChatEvent | { kind: "user" | "note"; text: string })[] {
  const out: (ChatEvent | { kind: "user" | "note"; text: string })[] = [];
  for (const it of items) {
    if (it.kind === "user" || it.kind === "note") out.push({ kind: it.kind, text: str(it.text) });
    else if (it.kind === "assistant") out.push({ kind: "text", text: str(it.text) });
    else if (it.kind === "thinking") out.push({ kind: "thinking", text: str(it.text) });
    else if (it.kind === "tool") out.push({ kind: "tool", id: str(it.id), label: str(it.label ?? it.name), toolKind: "" });
    else if (it.kind === "tool_result") out.push({ kind: "tool_done", id: str(it.id), ok: it.ok !== false, summary: str(it.text), refs: it.refs ?? {} });
    else if (it.kind === "card" && it.action) out.push({ kind: "card", card: actionCard(it.action) });
  }
  return out;
}

/** Which context panel a tool result points at, most specific first. */
export function panelFor(refs: Refs): { panel: "experiment" | "impact" | "claim"; id: string } | null {
  if (refs.experiment_id) return { panel: "experiment", id: refs.experiment_id };
  if (refs.impact_id) return { panel: "impact", id: refs.impact_id };
  if (refs.claim_id) return { panel: "claim", id: refs.claim_id };
  return null;
}

/** The research focus for a Studio workspace: ``<clade>.senses.<sense>``. */
export const focusPath = (clade: string, sense: string): string => `${clade}.senses.${sense}`;

/** The start screen narrowed to this clade; this sense's values first. */
export function startFor(start: Start, clade: string, sense: string): { values: LeastVerified[]; questions: OpenQuestion[] } {
  const focus = focusPath(clade, sense);
  const inClade = (p: string | null) => Boolean(p && (p === clade || p.startsWith(`${clade}.`)));
  const values = start.least_verified
    .filter((v) => inClade(v.library_path))
    .sort((a, b) => Number(!a.library_path.startsWith(focus)) - Number(!b.library_path.startsWith(focus)));
  const questions = start.open_questions.filter((q) => inClade(q.target) || q.hypothesis_id.includes(`:${clade}-`) || q.hypothesis_id.includes(`:${clade}.`));
  return { values, questions };
}

/** A rate as a percentage, or a dash. */
export const pct = (v: number | null | undefined): string => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

/** "baseline → patched" for a pair of numbers, formatted. */
export function arrow(before: number | null, after: number | null, fmt: (v: number | null) => string = pct): string {
  return `${fmt(before)} → ${fmt(after)}`;
}
