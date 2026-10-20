// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Pure formatting helpers (unit-tested with node --test).

export interface ProvLike {
  source_file: string;
  line_or_key: number | string | null;
}

/** "profiles/library/<clade>.yaml:27" or "file · key". */
export function whereLabel(p: ProvLike): string {
  if (typeof p.line_or_key === "number") return `${p.source_file}:${p.line_or_key}`;
  if (p.line_or_key) return `${p.source_file} · ${p.line_or_key}`;
  return p.source_file;
}

/** A library value as written: scalars as-is, intervals as "a–b", big numbers grouped. */
export function value(v: unknown): string {
  const one = (x: unknown) => (typeof x === "number" ? (Math.abs(x) >= 10000 ? x.toLocaleString("en-US") : String(x)) : String(x));
  if (Array.isArray(v)) return v.length === 2 ? `${one(v[0])}–${one(v[1])}` : v.map(one).join(", ");
  return one(v);
}

/** "step 3/10" or "step —". */
export function step(n: number | null | undefined, total: number | null | undefined): string {
  return n && total ? `step ${n}/${total}` : "step —";
}

/** A date or ISO timestamp as YYYY-MM-DD. */
export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

/** Plain words for a sense state. */
export function stateLabel(state: string): string {
  return ({ modelled: "modelled", described: "described", empty: "empty" } as Record<string, string>)[state] ?? state;
}

/** Plain words for the data badge. */
export function dataLabel(data: string): string {
  return ({ available: "data available", synthetic: "synthetic only", none: "no data stream" } as Record<string, string>)[data] ?? data;
}

/** Library field slots in plain words; unknown slots read as their own name with spaces. */
export function slotLabel(slot: string): string {
  const known: Record<string, string> = {
    detection_threshold: "detection threshold",
    range: "range",
    latency_ms: "latency",
    bandwidth: "temporal bandwidth",
    spatial_resolution: "spatial resolution",
    field_of_view_deg: "field of view",
  };
  return known[slot] ?? slot.replaceAll("_", " ").replaceAll(".", " · ");
}

/** "a12b34c…" for long hashes. */
export function short(h: string | null | undefined, n = 12): string {
  return h ? (h.length > n ? `${h.slice(0, n)}…` : h) : "—";
}

/** ms with one decimal, or "—". */
export function ms(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)} ms` : "—";
}

/** Percentage from a 0..1 fraction, or "—". */
export function pct(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? `${Math.round(v * 100)}%` : "—";
}
