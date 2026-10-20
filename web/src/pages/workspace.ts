// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Workspace /studio/{clade}/{sense}/{tab}: a persistent header (species, sense, pipeline step,
// certificate badge) and one tab at a time. Tabs are links; the URL is the state.

import { api, type Card, type Health, type Pipeline } from "../api.ts";
import { topbar } from "../chrome.ts";
import { badge, el, errorBox } from "../dom.ts";
import { step } from "../format.ts";
import { modelTab } from "../tabs/model.ts";
import { pipelineTab } from "../tabs/pipeline.ts";
import { researchTab } from "../tabs/research.ts";
import { runTab } from "../tabs/run.ts";
import { sourcesTab } from "../tabs/sources.ts";
import { useCasesTab } from "../tabs/usecases.ts";

export const TABS = [
  { id: "sources", label: "Sources" },
  { id: "model", label: "Model" },
  { id: "run", label: "Run" },
  { id: "pipeline", label: "Pipeline" },
  { id: "use-cases", label: "Use cases" },
  { id: "research", label: "Research" },
] as const;
export type TabId = (typeof TABS)[number]["id"];

function header(clade: string, sense: string, card: Card | undefined, pl: Pipeline | null): HTMLElement {
  const h = el("section", "ws-head");
  const t = el("div", "ws-title");
  const name = card?.names[0] ?? clade;
  t.append(el("h1", undefined, `${name} · ${sense}`));
  if (card?.latin) t.append(el("span", "latin", card.latin));
  const chip = card?.senses.find((s) => s.id === sense);
  const b = el("div", "badges");
  if (chip) b.append(badge(chip.state, chip.state === "modelled" ? "teal" : chip.state === "described" ? "muted" : "warn"));
  if (pl) {
    const sb = badge(`pipeline ${step(pl.at, pl.total)}`, "muted", pl.steps.find((s) => s.n === pl.at)?.name ?? "");
    sb.dataset.testid = "pipeline-step";
    b.append(sb);
    const cert = pl.steps.find((s) => s.id === "certificate");
    b.append(cert?.done ? badge("certified", "teal", cert.detail) : badge("no certificate", "muted", cert?.detail ?? "no certificate step"));
  }
  h.append(t, b);
  return h;
}

export async function workspacePage(root: HTMLElement, clade: string, sense: string, tab: TabId): Promise<void> {
  const main = el("main", "workspace");
  root.replaceChildren(topbar(`${clade} · ${sense}`, [["All species", "/studio"]]), main);
  const [sp, pl, health] = await Promise.all([
    api.species().catch(() => null),
    api.pipeline(clade, sense).catch((e: unknown) => e as Error),
    api.health().catch(() => null as Health | null),
  ]);
  if (pl instanceof Error) {
    main.append(errorBox(pl));
    return;
  }
  const card = sp?.cards.find((c) => c.clade === clade);
  main.append(header(clade, sense, card, pl));

  const research = Boolean(health?.research.configured);
  const nav = el("nav", "tabs");
  nav.setAttribute("aria-label", "Workspace");
  for (const t of TABS) {
    if (t.id === "research" && !research) continue;
    const a = el("a", undefined, t.label);
    a.href = `/studio/${encodeURIComponent(clade)}/${encodeURIComponent(sense)}/${t.id}`;
    a.dataset.tab = t.id;
    if (t.id === tab) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  const body = el("div", "tab-body");
  main.append(nav, body);
  body.append(el("p", "loading muted", "loading…"));
  try {
    if (tab === "sources") await sourcesTab(body, clade, sense);
    else if (tab === "model") await modelTab(body, clade, sense);
    else if (tab === "run") await runTab(body, clade, sense);
    else if (tab === "pipeline") pipelineTab(body, pl);
    else if (tab === "use-cases") await useCasesTab(body, clade, sense);
    else if (tab === "research") {
      if (research) researchTab(body, clade, sense);
      else body.replaceChildren(el("p", "muted", "Research is not configured on this server (RESEARCH_URL unset)."));
    }
  } catch (e) {
    body.replaceChildren(errorBox(e));
  }
}
