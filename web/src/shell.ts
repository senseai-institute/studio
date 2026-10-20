// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// The application shell: top bar (brand, breadcrumbs, search, provenance and theme toggles,
// help), the sidebar index of every species and sense, and the main column. Keyboard:
//   /  search      p  show provenance      t  light/dark      ?  shortcuts
//   1–6 workspace tabs      Esc  close search

import { api, type Species } from "./api.ts";
import { el } from "./dom.ts";
import { step } from "./format.ts";

let speciesCache: Promise<Species> | null = null;
export function species(): Promise<Species> {
  speciesCache ??= api.species();
  return speciesCache;
}

function store(key: string, value?: string): string | null {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch {
    /* private mode: the toggle still works for this page */
  }
  return value ?? null;
}

function applyPrefs(): void {
  const theme = store("studio.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  document.body.classList.toggle("show-prov", store("studio.prov") === "1");
}

function toggleTheme(): void {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store("studio.theme", next);
}

function toggleProv(btn?: HTMLElement): void {
  const on = !document.body.classList.contains("show-prov");
  document.body.classList.toggle("show-prov", on);
  store("studio.prov", on ? "1" : "0");
  (btn ?? document.querySelector<HTMLElement>("#prov-toggle"))?.setAttribute("aria-pressed", String(on));
}

function helpDialog(): HTMLDialogElement {
  const d = el("dialog", "help");
  d.setAttribute("aria-label", "Keyboard shortcuts");
  const dlist = el("dl");
  for (const [k, v] of [
    ["/", "search species and senses"],
    ["1 – 6", "switch workspace tab"],
    ["p", "show where every item came from (file:line)"],
    ["t", "light / dark"],
    ["?", "this help"],
  ]) {
    const dt = el("dt");
    dt.append(el("kbd", undefined, k));
    dlist.append(dt, el("dd", undefined, v));
  }
  const close = el("button", "btn", "Close");
  close.addEventListener("click", () => d.close());
  d.append(el("h2", undefined, "Keyboard"), dlist, close);
  document.body.append(d);
  return d;
}

interface Hit {
  label: string;
  sub: string;
  href: string;
  hay: string;
}

function searchBox(): HTMLElement {
  const wrap = el("div", "search");
  const input = el("input");
  input.type = "search";
  input.placeholder = "Species or sense";
  input.setAttribute("aria-label", "Search species and senses");
  input.id = "search";
  const kbd = el("kbd", "hide-narrow", "/");
  const list = el("ul", "search-results");
  list.hidden = true;
  wrap.append(input, kbd, list);
  let hits: Hit[] = [];
  let sel = 0;
  const all = species().then((sp) =>
    sp.cards.flatMap((c) => [
      { label: c.names[0] ?? c.clade, sub: c.latin ?? c.clade, href: `/studio/${c.clade}`, hay: [c.clade, c.latin, ...c.names, ...c.representative.map((r) => `${r.name} ${r.common_name ?? ""}`)].join(" ").toLowerCase() },
      ...c.senses.map((s) => ({
        label: `${c.names[0] ?? c.clade} · ${s.id}`,
        sub: `${s.state} · ${step(s.step, s.steps)}`,
        href: `/studio/${c.clade}/${s.id}`,
        hay: [c.clade, c.latin, ...c.names, s.id, s.modality].join(" ").toLowerCase(),
      })),
    ]),
  );
  const render = () => {
    list.replaceChildren();
    hits.forEach((h, i) => {
      const li = el("li");
      const a = el("a");
      a.href = h.href;
      a.append(el("span", undefined, h.label), el("span", "faint", h.sub));
      if (i === sel) a.setAttribute("aria-selected", "true");
      li.append(a);
      list.append(li);
    });
    list.hidden = !hits.length;
  };
  input.addEventListener("input", async () => {
    const q = input.value.trim().toLowerCase();
    const items = await all;
    hits = q ? items.filter((h) => q.split(/\s+/).every((w) => h.hay.includes(w))).slice(0, 12) : [];
    sel = 0;
    render();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") sel = Math.min(sel + 1, hits.length - 1);
    else if (e.key === "ArrowUp") sel = Math.max(sel - 1, 0);
    else if (e.key === "Enter" && hits[sel]) location.href = hits[sel].href;
    else if (e.key === "Escape") {
      input.value = "";
      hits = [];
      input.blur();
    } else return;
    e.preventDefault();
    render();
  });
  input.addEventListener("blur", () => window.setTimeout(() => (list.hidden = true), 150));
  return wrap;
}

async function sidebar(current?: { clade?: string; sense?: string }): Promise<HTMLElement> {
  const nav = el("nav", "sidebar");
  nav.setAttribute("aria-label", "Index of species and senses");
  nav.append(el("h2", undefined, "Index"));
  try {
    const sp = await species();
    for (const c of sp.cards) {
      const box = el("div", "idx-clade");
      const a = el("a");
      a.href = `/studio/${encodeURIComponent(c.clade)}`;
      a.append(c.names[0] ?? c.clade, el("span", "latin", c.latin ?? ""));
      const ul = el("ul");
      for (const s of c.senses) {
        const li = el("li");
        const sa = el("a");
        sa.href = `/studio/${encodeURIComponent(c.clade)}/${encodeURIComponent(s.id)}`;
        sa.title = `${s.state} · ${s.values} cited value(s) · ${step(s.step, s.steps)}`;
        sa.append(el("span", `dot ${s.state}`), s.id, el("span", "step", `${s.step}/${s.steps}`));
        if (current?.clade === c.clade && current.sense === s.id) sa.setAttribute("aria-current", "page");
        li.append(sa);
        ul.append(li);
      }
      box.append(a, ul);
      nav.append(box);
    }
    const key = el("div", "key");
    for (const [cls, text] of [
      ["modelled", "modelled: a profile reads it"],
      ["described", "described: cited values only"],
      ["empty", "empty: nothing cited yet"],
    ]) {
      const s = el("span");
      s.append(el("span", `dot ${cls}`), text);
      key.append(s);
    }
    nav.append(key);
  } catch {
    nav.append(el("p", "empty", "Index unavailable."));
  }
  return nav;
}

export interface Shell {
  main: HTMLElement;
  page: HTMLElement;
}

/** Build the shell into `root`; returns the page column to fill. */
export async function shell(root: HTMLElement, crumbs: [string, string | null][], current?: { clade?: string; sense?: string }): Promise<Shell> {
  applyPrefs();
  const frame = el("div", "shell");
  const top = el("header", "topbar");
  const brand = el("a", "brand");
  brand.href = "/studio";
  brand.append(el("span", "brand-mark"), "SenseAI Studio");
  const menu = el("button", "icon-btn only-narrow", "Index");
  menu.type = "button";
  menu.addEventListener("click", () => frame.classList.toggle("index-open"));
  const cr = el("nav", "crumbs");
  cr.setAttribute("aria-label", "Breadcrumbs");
  crumbs.forEach(([label, href], i) => {
    if (i) cr.append(el("span", undefined, "/"));
    if (href) {
      const a = el("a", undefined, label);
      a.href = href;
      cr.append(a);
    } else cr.append(el("span", undefined, label));
  });
  const tools = el("div", "top-tools");
  const prov = el("button", "icon-btn hide-narrow", "Provenance");
  prov.id = "prov-toggle";
  prov.type = "button";
  prov.title = "Show the file and line behind every item (p)";
  prov.setAttribute("aria-pressed", String(document.body.classList.contains("show-prov")));
  prov.addEventListener("click", () => toggleProv(prov));
  const theme = el("button", "icon-btn", "Theme");
  theme.type = "button";
  theme.title = "Light / dark (t)";
  theme.setAttribute("aria-label", "Toggle light or dark theme");
  theme.addEventListener("click", toggleTheme);
  const help = el("button", "icon-btn hide-narrow", "?");
  help.type = "button";
  help.title = "Keyboard shortcuts";
  const dialog = helpDialog();
  help.addEventListener("click", () => dialog.showModal());
  tools.append(searchBox(), prov, theme, help);
  top.append(brand, menu, cr, tools);
  const main = el("main", "main");
  const page = el("div", "page");
  main.append(page);
  frame.append(top, await sidebar(current), main);
  root.replaceChildren(frame);

  document.addEventListener("keydown", (e) => {
    const t = e.target as HTMLElement;
    if (t.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") {
      e.preventDefault();
      document.querySelector<HTMLInputElement>("#search")?.focus();
    } else if (e.key === "?") dialog.showModal();
    else if (e.key === "p") toggleProv(prov);
    else if (e.key === "t") toggleTheme();
    else if (/^[1-6]$/.test(e.key)) document.querySelectorAll<HTMLAnchorElement>(".tabs a")[Number(e.key) - 1]?.click();
  });
  return { main, page };
}
