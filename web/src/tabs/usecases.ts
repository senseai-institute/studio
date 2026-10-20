// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Use cases: founder-written Markdown, with the pipeline step beside every claim (each list
// item) so a reader sees how far the evidence behind it has come.

import { api } from "../api.ts";
import { badge, el, empty, from, inspect, panel } from "../dom.ts";
import { step } from "../format.ts";

export async function useCasesTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const res = await api.useCases(clade, sense);
  body.replaceChildren();
  if (!res.items.length) {
    const p = panel("Use cases");
    p.body.append(empty(`Nothing written yet. Add ${res.template_file} (senseai-studio check --write-templates creates it).`));
    body.append(p.box);
  }
  res.items.forEach((u, i) => {
    const p = panel(u.niche);
    p.head.append(badge(u.status ?? "no status", u.status === "validated" ? "teal" : "warn"), badge(step(res.step, res.steps), "muted"));
    if (u.template) p.head.append(badge("template: not written yet", "muted"));
    if (u.evidence.length) p.head.append(badge(`evidence: ${u.evidence.join(", ")}`, "teal"));
    const doc = el("div", "markdown");
    doc.innerHTML = u.html; // server-rendered with raw HTML disabled (markdown-it, html: false)
    doc.querySelectorAll("li").forEach((li) => {
      const b = badge(step(res.step, res.steps), "muted", "how far this species+sense is through the pipeline");
      b.classList.add("claim-step");
      li.append(" ", b);
    });
    from(doc, res, `items/${i}/html`);
    p.body.append(doc, el("span", "src mono", u.file));
    body.append(p.box);
  });
  body.append(inspect(res));
}
