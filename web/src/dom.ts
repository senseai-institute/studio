// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// DOM helpers, badges and the "where did this come from" affordances shared by every screen.

import type { Prov, WithProv } from "./api.ts";
import { whereLabel } from "./format.ts";

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export type Tone = "teal" | "warn" | "alert" | "muted";

/** A caveat or state, always visible: honest badges are the rule, not the exception. */
export function badge(text: string, tone: Tone = "muted", title?: string): HTMLSpanElement {
  const b = el("span", `badge ${tone}`, text);
  if (title) b.title = title;
  return b;
}

export function link(text: string, href: string, external = false): HTMLAnchorElement {
  const a = el("a", undefined, text);
  a.href = href;
  if (external) {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  }
  return a;
}

export function panel(title: string, cls = ""): { box: HTMLElement; head: HTMLElement; body: HTMLElement } {
  const box = el("section", `panel ${cls}`.trim());
  const head = el("h2", undefined, title);
  const body = el("div", "panel-body");
  box.append(head, body);
  return { box, head, body };
}

/** Provenance of one field (exact match first, then the nearest parent path). */
export function provOf(res: WithProv, field: string): Prov[] {
  const exact = res.provenance.filter((p) => p.field === field);
  if (exact.length) return exact;
  const parts = field.split("/");
  while (parts.length > 1) {
    parts.pop();
    const f = parts.join("/");
    const hit = res.provenance.filter((p) => p.field === f);
    if (hit.length) return hit;
  }
  return [];
}

/** Attach "where from" to an element: a tooltip and a data attribute the tests read. */
export function from(e: HTMLElement, res: WithProv, field: string): HTMLElement {
  const ps = provOf(res, field);
  if (ps.length) {
    e.title = ps.map(whereLabel).join("\n");
    e.dataset.source = ps.map(whereLabel).join(" ");
  }
  return e;
}

/** A small "source" chip naming the file and line an item came from. */
export function sourceChip(res: WithProv, field: string): HTMLElement {
  const ps = provOf(res, field);
  const s = el("span", "src mono", ps.length ? whereLabel(ps[0]) : "source not recorded");
  if (ps.length > 1) s.title = ps.map(whereLabel).join("\n");
  return s;
}

/** The "inspect" toggle: raw JSON and provenance of a response, hidden by default. */
export function inspect(res: unknown): HTMLElement {
  const d = el("details", "inspect");
  const s = el("summary", undefined, "Inspect (raw data and provenance)");
  const pre = el("pre", "mono");
  d.append(s, pre);
  d.addEventListener("toggle", () => {
    if (d.open && !pre.textContent) pre.textContent = JSON.stringify(res, null, 2);
  });
  return d;
}

export function empty(text: string): HTMLElement {
  return el("p", "empty muted", text);
}

export function errorBox(e: unknown): HTMLElement {
  return el("p", "error", `Could not load: ${e instanceof Error ? e.message : String(e)}`);
}

export function dl(rows: [string, Node | string | null | undefined][]): HTMLDListElement {
  const d = el("dl", "kv");
  for (const [k, v] of rows) {
    if (v === null || v === undefined || v === "") continue;
    d.append(el("dt", undefined, k));
    const dd = el("dd");
    dd.append(v);
    d.append(dd);
  }
  return d;
}
