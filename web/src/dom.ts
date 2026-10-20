// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// DOM helpers, honest tags and the provenance affordances shared by every screen.

import type { Prov, WithProv } from "./api.ts";
import { whereLabel } from "./format.ts";

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export type Tone = "teal" | "warn" | "alert" | "muted" | "plain" | "measured" | "proposed" | "physics";

/** A caveat or state, always visible: honest tags are the rule, not the exception. */
export function badge(text: string, tone: Tone = "plain", title?: string): HTMLSpanElement {
  const b = el("span", `tag ${tone}`, text);
  if (title) b.title = title;
  return b;
}

export function tags(...items: (Node | string | null | undefined | false)[]): HTMLSpanElement {
  const s = el("span", "tags");
  for (const i of items) if (i) s.append(i);
  return s;
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

/** A numbered section with a serif heading and an optional tool slot (filters, tags). */
export function section(num: string, title: string, id?: string): { box: HTMLElement; head: HTMLElement; tools: HTMLElement; body: HTMLElement } {
  const box = el("section", "section");
  if (id) box.id = id;
  const head = el("header");
  const tools = el("div", "tools");
  head.append(el("span", "num", num), el("h2", undefined, title), tools);
  const body = el("div", "section-body");
  body.style.display = "grid";
  body.style.gap = "12px";
  box.append(head, body);
  return { box, head, tools, body };
}

/** Back-compatible alias: a section without a number. */
export function panel(title: string): { box: HTMLElement; head: HTMLElement; body: HTMLElement } {
  const s = section("", title);
  s.box.classList.add("panel");
  return { box: s.box, head: s.tools, body: s.body };
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
    e.title = [e.title, ...ps.map(whereLabel)].filter(Boolean).join("\n");
    e.dataset.source = ps.map(whereLabel).join(" ");
  }
  return e;
}

let toastEl: HTMLElement | null = null;
export function toast(text: string): void {
  toastEl ??= document.body.appendChild(el("div", "toast"));
  toastEl.textContent = text;
  toastEl.classList.add("on");
  window.setTimeout(() => toastEl?.classList.remove("on"), 1400);
}

export function copy(text: string, what = "Copied"): void {
  const done = () => toast(`${what}: ${text.length > 60 ? `${text.slice(0, 57)}…` : text}`);
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, () => toast("Copy failed"));
  else toast(text);
}

/** "↳ file:line", click to copy. `optional` ones show only with provenance on (p). */
export function srcRef(label: string | null | undefined, optional = false): HTMLElement {
  const b = el("button", `src${optional ? " opt" : ""}`, label ?? "source not recorded");
  b.type = "button";
  b.title = "Where this came from. Click to copy.";
  if (label) b.addEventListener("click", (e) => {
    e.stopPropagation();
    copy(label, "Source");
  });
  return b;
}

/** The pointer for a response field. */
export function sourceChip(res: WithProv, field: string, optional = true): HTMLElement {
  const ps = provOf(res, field);
  const s = srcRef(ps.length ? whereLabel(ps[0]) : null, optional);
  if (ps.length > 1) s.title = `${ps.map(whereLabel).join("\n")}\nClick to copy the first.`;
  return s;
}

/** The "inspect" toggle: raw data and provenance of a response, hidden by default. */
export function inspect(res: unknown): HTMLElement {
  const d = el("details", "inspect");
  const s = el("summary", undefined, "Inspect the raw response (JSON with provenance)");
  const pre = el("pre", "mono");
  d.append(s, pre);
  d.addEventListener("toggle", () => {
    if (d.open && !pre.textContent) pre.textContent = JSON.stringify(res, null, 2);
  });
  return d;
}

export function empty(text: string): HTMLElement {
  return el("p", "empty", text);
}

export function errorBox(e: unknown): HTMLElement {
  return el("p", "note alert", `Could not load: ${e instanceof Error ? e.message : String(e)}`);
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

export function table(head: (string | [string, string])[]): { wrap: HTMLElement; t: HTMLTableElement; tb: HTMLTableSectionElement } {
  const wrap = el("div", "table-wrap");
  const t = el("table", "data");
  const th = el("thead");
  const tr = el("tr");
  for (const h of head) {
    const [label, cls] = Array.isArray(h) ? h : [h, ""];
    tr.append(el("th", cls || undefined, label));
  }
  th.append(tr);
  const tb = el("tbody");
  t.append(th, tb);
  wrap.append(t);
  return { wrap, t, tb };
}

export function td(content: Node | string, cls?: string): HTMLTableCellElement {
  const c = el("td", cls);
  c.append(content);
  return c;
}

/** Plain-language tone for a world/circuit parameter kind. */
export function kindTag(kind: string): HTMLSpanElement {
  const tips: Record<string, string> = {
    measured: "a value reported in a cited paper",
    proposed: "a flagged placeholder: the literature describes it, no citable value yet",
    physics: "true for any observer, or a unit choice",
  };
  const tone: Tone = kind === "measured" ? "measured" : kind === "proposed" ? "proposed" : "physics";
  return badge(kind, tone, tips[kind] ?? "");
}
