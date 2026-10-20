// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Sources: every cited value of the sense, the paper behind it, its verification status, and
// what is still open.

import { api, type Citation, type Sources } from "../api.ts";
import { badge, dl, el, empty, from, inspect, link, panel, sourceChip } from "../dom.ts";
import { slotLabel, value } from "../format.ts";

function cite(c: Citation): HTMLElement {
  const li = el("li", "cite");
  if (!c.found) {
    li.append(c.link ? link(c.id, c.link, true) : el("span", "mono", c.id), " ", badge("not in CITATIONS.md", "warn"));
    return li;
  }
  const who = el("span", "who", `${c.authors ?? ""}${c.year ? ` (${c.year})` : ""}`);
  li.append(who, " ");
  if (c.title) li.append(el("span", "title", c.title), " ");
  if (c.link) li.append(link(c.id.startsWith("10.") ? `doi:${c.id}` : "link", c.link, true), " ");
  if (c.checked) li.append(badge(`read: ${c.checked}`, c.checked === "abstract" || c.checked === "full page" ? "muted" : "warn", "how much of the paper was read to confirm the value (CITATIONS.md, Checked)"));
  return li;
}

function verification(v: Sources["quantities"][number]["verification"]): HTMLElement {
  if (!v.tabled) return badge("not tabled", "muted", "no row in the P0 evidence table for this value");
  const tone = v.status === "verified" ? "teal" : v.status === "disputed" ? "alert" : "warn";
  return badge(v.status, tone, "status in the evidence table");
}

export async function sourcesTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const res = await api.sources(clade, sense);
  body.replaceChildren();
  const info = panel("This sense");
  info.body.append(
    dl([
      ["organ", res.sense_info.organ ? from(el("span", undefined, res.sense_info.organ), res, "sense/organ") : null],
      ["signal", res.sense_info.signal ?? null],
      ["modality", res.sense_info.modality ?? null],
      ["notes", res.sense_info.notes ? from(el("span", undefined, res.sense_info.notes), res, "sense/notes") : null],
    ]),
  );
  const tb = el("p", "table-status");
  if (res.table.present) tb.append(badge(`evidence table: ${res.table.verified} of ${res.table.total} rows verified`, res.table.verified === res.table.total ? "teal" : "warn"), " ", el("span", "src mono", res.table.file));
  else tb.append(badge("no evidence table yet", "muted", res.table.file), " ", el("span", "muted", "verification status and verbatim quotes appear once the P0 table exists"));
  if (res.review_status === "draft") tb.append(" ", badge("library entry: draft", "warn", "not yet checked by a domain expert"));
  info.body.append(tb);
  body.append(info.box);

  const qs = panel(`Measured values (${res.quantities.length})`);
  if (!res.quantities.length) qs.body.append(empty("No cited value for this sense in the library yet."));
  res.quantities.forEach((q, i) => {
    const row = el("article", "quantity");
    row.dataset.path = q.path;
    const top = el("div", "q-top");
    const v = el("span", "q-value mono", `${value(q.value)} ${q.unit}`);
    from(v, res, `quantities/${i}/value`);
    top.append(el("span", "q-name", q.description ?? slotLabel(q.slot)), v, verification(q.verification));
    top.append(badge(`confidence: ${q.confidence}`, q.confidence === "high" ? "teal" : q.confidence === "low" ? "alert" : "muted"));
    if (q.consumers.length) top.append(badge(`read by ${[...new Set(q.consumers.map((c) => c.profile))].join(", ")}`, "teal", q.consumers.map((c) => `${c.profile}.${c.section}.${c.field} (${c.rule})`).join("\n")));
    row.append(top);
    row.append(
      dl([
        ["species", q.species ? el("i", undefined, q.species) : null],
        ["conditions", q.conditions],
        ["notes", q.notes],
        ["quote", q.verification.quote ? el("q", undefined, q.verification.quote) : null],
      ]),
    );
    const ul = el("ul", "cites");
    const seen = new Set<string>();
    q.citations.forEach((c) => {
      const key = c.reference ?? c.id;
      if (seen.has(key)) return; // a DOI and its PMC link name the same CITATIONS.md row
      seen.add(key);
      ul.append(cite(c));
    });
    row.append(ul, sourceChip(res, `quantities/${i}/value`));
    qs.body.append(row);
  });
  body.append(qs.box);

  const oq = panel(`Open questions (${res.open_questions.length + res.requests.length})`);
  if (!res.open_questions.length && !res.requests.length) oq.body.append(empty("None recorded."));
  const ul = el("ul", "questions");
  res.open_questions.forEach((q, i) => {
    const li = el("li");
    li.append(badge(q.scope, "muted"), " ", q.text);
    from(li, res, `open_questions/${i}`);
    ul.append(li);
  });
  res.requests.forEach((r, i) => {
    const li = el("li");
    li.append(badge(`request · ${r.status}`, r.status === "answered" ? "teal" : "muted"), " ");
    if (r.priority) li.append(badge(r.priority, r.priority === "critical" ? "alert" : r.priority === "high" ? "warn" : "muted"), " ");
    li.append(r.question, " ", el("span", "src mono", r.id));
    from(li, res, `requests/${i}`);
    ul.append(li);
  });
  oq.body.append(ul);
  body.append(oq.box, inspect(res));
}
