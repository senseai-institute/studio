// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Workspace /studio/{clade}/{sense}/{tab}: an abstract-style header (what this sense is, the
// counts that matter, the pipeline stepper, the honest tags) and one tab at a time. Tabs are
// links (the URL is the state) and keys 1–6.

import { api, type Card, type Health, type Pipeline } from "../api.ts";
import { badge, el, errorBox, tags } from "../dom.ts";
import { modelTab } from "../tabs/model.ts";
import { pipelineTab } from "../tabs/pipeline.ts";
import { researchTab } from "../tabs/research.ts";
import { runTab } from "../tabs/run.ts";
import { sourcesTab } from "../tabs/sources.ts";
import { useCasesTab } from "../tabs/usecases.ts";
import { shell, species } from "../shell.ts";

export const TABS = [
  { id: "sources", label: "Sources" },
  { id: "model", label: "Model" },
  { id: "run", label: "Run" },
  { id: "pipeline", label: "Pipeline" },
  { id: "use-cases", label: "Use cases" },
  { id: "research", label: "Research" },
] as const;
export type TabId = (typeof TABS)[number]["id"];

function fact(v: string | number, k: string): HTMLElement {
  const f = el("div", "fact");
  f.append(el("div", "v", String(v)), el("div", "k", k));
  return f;
}

function abstract(clade: string, sense: string, card: Card | undefined, pl: Pipeline): HTMLElement {
  const box = el("section", "abstract");
  const chip = card?.senses.find((s) => s.id === sense);
  const row = el("div", "title-row");
  const h = el("h1", "page-title", `${card?.names[0] ?? clade} · ${sense}`);
  if (card?.latin) h.append(el("span", "latin", card.latin));
  const cert = pl.steps.find((s) => s.id === "certificate");
  const stepTag = badge(`pipeline step ${pl.at}/${pl.total}`, "plain", pl.steps.find((s) => s.n === pl.at)?.name ?? "");
  stepTag.dataset.testid = "pipeline-step";
  row.append(
    h,
    tags(
      chip ? badge(chip.state, chip.state === "modelled" ? "teal" : chip.state === "described" ? "muted" : "warn", chip.state === "modelled" ? `read by ${chip.profiles.join(", ")}` : "") : null,
      chip ? badge(chip.data === "available" ? `${chip.recordings} recording(s)` : chip.data === "synthetic" ? "synthetic data only" : "no data stream", chip.data === "available" ? "teal" : "warn") : null,
      stepTag,
      cert?.done ? badge("certified", "teal", cert.detail) : badge("not certified", "muted", cert?.detail ?? ""),
    ),
  );
  box.append(row);
  const rep = card?.representative.map((r) => (r.common_name ? `${r.common_name} (${r.name})` : r.name)).join("; ");
  if (rep) {
    const p = el("p", "lede");
    p.append("Measurements mostly from the ", el("span", "latin", rep), ".");
    box.append(p);
  }
  const facts = el("div", "facts");
  if (chip) {
    facts.append(
      fact(chip.values, "cited values"),
      fact(chip.sources, "sources cited"),
      fact(chip.profiles.length, chip.profiles.length === 1 ? "profile reads it" : "profiles read it"),
      fact(chip.open_questions, "open questions"),
    );
  }
  facts.append(fact(pl.clock.days === null ? "—" : `${pl.clock.days} d`, pl.clock.partial ? "pipeline clock (partial)" : "pipeline clock"));
  box.append(facts);
  const stepper = el("div", "stepper");
  stepper.style.setProperty("--n", String(pl.total));
  for (const s of pl.steps) {
    const i = el("i", s.done ? "done" : s.n === pl.at ? "current" : "");
    i.title = `${s.n}. ${s.name}: ${s.done ? "done" : s.detail}`;
    stepper.append(i);
  }
  const lab = el("div", "stepper-label");
  const cur = pl.steps.find((s) => s.n === pl.at);
  lab.append(el("span", undefined, cur ? `Step ${cur.n} of ${pl.total}: ${cur.name}${pl.complete ? " (complete)" : ""}` : ""), el("span", undefined, `${pl.steps.filter((s) => s.done).length} of ${pl.total} steps done`));
  box.append(stepper, lab);
  return box;
}

export async function cladePage(root: HTMLElement, clade: string): Promise<void> {
  const sp = await species();
  const c = sp.cards.find((x) => x.clade === clade);
  const first = c?.senses.find((s) => s.state === "modelled") ?? c?.senses[0];
  if (c && first) location.replace(`/studio/${encodeURIComponent(clade)}/${encodeURIComponent(first.id)}`);
  else root.replaceChildren(el("main", "loading", `No library entry “${clade}”.`));
}

export async function workspacePage(root: HTMLElement, clade: string, sense: string, tab: TabId): Promise<void> {
  const [sp, pl, health] = await Promise.all([
    species().catch(() => null),
    api.pipeline(clade, sense).catch((e: unknown) => e as Error),
    api.health().catch(() => null as Health | null),
  ]);
  const card = sp?.cards.find((c) => c.clade === clade);
  const { page } = await shell(
    root,
    [["Atlas", "/studio"], [card?.names[0] ?? clade, `/studio/${encodeURIComponent(clade)}`], [sense, null]],
    { clade, sense },
  );
  if (pl instanceof Error) {
    page.append(errorBox(pl));
    return;
  }
  page.append(abstract(clade, sense, card, pl));

  const research = Boolean(health?.research.configured);
  const nav = el("nav", "tabs");
  nav.setAttribute("aria-label", "Workspace");
  let n = 0;
  for (const t of TABS) {
    if (t.id === "research" && !research) continue;
    const a = el("a");
    a.append(t.label, el("kbd", "hide-narrow", String(++n)));
    a.href = `/studio/${encodeURIComponent(clade)}/${encodeURIComponent(sense)}/${t.id}`;
    a.dataset.tab = t.id;
    if (t.id === tab) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  const body = el("div", "tab-body");
  page.append(nav, body);
  body.append(el("p", "loading", "loading…"));
  try {
    if (tab === "sources") await sourcesTab(body, clade, sense);
    else if (tab === "model") await modelTab(body, clade, sense);
    else if (tab === "run") await runTab(body, clade, sense);
    else if (tab === "pipeline") pipelineTab(body, pl);
    else if (tab === "use-cases") await useCasesTab(body, clade, sense);
    else if (tab === "research") {
      if (research) researchTab(body, clade, sense);
      else body.replaceChildren(el("p", "note", "Research is not configured on this server (RESEARCH_URL unset)."));
    }
  } catch (e) {
    body.replaceChildren(errorBox(e));
  }
}
