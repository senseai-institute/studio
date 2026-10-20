// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Use cases: founder-written Markdown, with the pipeline step beside every claim (each list
// item) so a reader sees how far the evidence behind it has come.

import { api } from "../api.ts";
import { badge, el, empty, from, inspect, section, srcRef } from "../dom.ts";
import { step } from "../format.ts";

export async function useCasesTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const res = await api.useCases(clade, sense);
  body.replaceChildren();
  const s = section("", "Use cases");
  s.tools.append(el("span", "faint small", "written by the founder · claims carry the pipeline step"));
  if (!res.items.length) s.body.append(empty(`Nothing written yet. Add ${res.template_file} (senseai-studio check --write-templates creates it).`));
  res.items.forEach((u, i) => {
    const doc = el("article", "doc");
    const head = el("header");
    head.append(
      el("h3", undefined, u.niche),
      badge(u.status ?? "no status", u.status === "validated" ? "teal" : "warn"),
      badge(step(res.step, res.steps), "plain"),
      u.template ? badge("template: not written yet", "muted") : "",
      u.evidence.length ? badge(`evidence: ${u.evidence.join(", ")}`, "teal") : badge("no evidence run linked", "muted"),
    );
    const md = el("div", "markdown");
    md.innerHTML = u.html; // server-rendered with raw HTML disabled (markdown-it, html: false)
    md.querySelectorAll("li").forEach((li) => {
      const b = badge(step(res.step, res.steps), "muted", "how far this species+sense is through the pipeline");
      b.classList.add("claim-step");
      li.append(" ", b);
    });
    from(md, res, `items/${i}/html`);
    doc.append(head, md, srcRef(u.file));
    s.body.append(doc);
  });
  body.append(s.box, inspect(res));
}
