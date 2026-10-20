// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Sources: every cited value of the sense as a table with numbered references, what is still
// open, and the bibliography (from library/CITATIONS.md). Rows expand to conditions, notes,
// the verbatim quote and which profile fields read the value.

import { api, type Citation, type QuantityRow, type Sources } from "../api.ts";
import { badge, copy, dl, el, empty, from, inspect, link, section, sourceChip, table, tags, td } from "../dom.ts";
import { slotLabel, value } from "../format.ts";

function refKey(c: Citation): string {
  return c.reference ?? c.id;
}

function verification(v: QuantityRow["verification"]): HTMLElement {
  if (!v.tabled) return badge("not tabled", "muted", "no row in the P0 evidence table for this value yet");
  const tone = v.status === "verified" ? "teal" : v.status === "disputed" ? "alert" : "warn";
  return badge(v.status, tone, "status in the evidence table");
}

function confidence(c: string): HTMLElement {
  return badge(c, c === "high" ? "teal" : c === "low" ? "alert" : "muted", "confidence the library entry gives this value");
}

function reference(c: Citation, n: number): HTMLLIElement {
  const li = el("li");
  li.id = `ref-${n}`;
  const body = el("div");
  if (c.found && c.reference) {
    const r = c.reference;
    const title = c.title ?? "";
    const i = title ? r.indexOf(title) : -1;
    if (i >= 0) body.append(r.slice(0, i), el("i", undefined, title), r.slice(i + title.length));
    else body.append(r);
  } else body.append(el("span", "mono", c.id));
  const meta = el("div", "meta");
  if (c.link) meta.append(link(c.link.replace(/^https?:\/\//, ""), c.link, true));
  if (c.checked) meta.append(badge(`read: ${c.checked}`, /secondary|record only|caption/.test(c.checked) ? "warn" : "muted", "how much of the paper was read to confirm the values (CITATIONS.md, Checked)"));
  if (!c.found) meta.append(badge("not in CITATIONS.md", "warn"));
  const cp = el("button", "link-btn", "copy reference");
  cp.type = "button";
  cp.addEventListener("click", () => copy([c.reference ?? c.id, c.link].filter(Boolean).join(" "), "Reference"));
  meta.append(cp);
  body.append(meta);
  li.append(el("span", "n", `[${n}]`), body);
  return li;
}

export async function sourcesTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const res: Sources = await api.sources(clade, sense);
  body.replaceChildren();

  // numbering: in order of first citation, values first, then the sense's own citations
  const order = new Map<string, number>();
  const refs: Citation[] = [];
  const num = (c: Citation) => {
    const k = refKey(c);
    if (!order.has(k)) {
      order.set(k, refs.length + 1);
      refs.push(c);
    }
    return order.get(k)!;
  };
  res.quantities.forEach((q) => q.citations.forEach(num));
  res.sense_info.citations.forEach(num);

  // §1 values
  const s1 = section("§1", `Measured values`);
  const filt = el("div", "filters");
  const seg = el("div", "seg");
  let level = "all";
  for (const lv of ["all", "high", "medium", "low"]) {
    const b = el("button", undefined, lv);
    b.type = "button";
    b.setAttribute("aria-pressed", String(lv === level));
    b.addEventListener("click", () => {
      level = lv;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      apply();
    });
    seg.append(b);
  }
  filt.append("confidence", seg);
  s1.tools.append(
    filt,
    res.table.present
      ? badge(`evidence table ${res.table.verified}/${res.table.total} verified`, res.table.verified === res.table.total && res.table.total ? "teal" : "warn", res.table.file)
      : badge("no evidence table yet", "muted", `${res.table.file}: verification status and verbatim quotes appear once it exists`),
  );
  if (!res.quantities.length) s1.body.append(empty("No cited value for this sense in the library yet."));
  else {
    const { wrap, tb } = table(["quantity", ["value", "num"], "species", "confidence", "verification", "refs"]);
    res.quantities.forEach((q, i) => {
      const tr = el("tr", "expandable quantity");
      tr.dataset.path = q.path;
      tr.dataset.confidence = q.confidence;
      if (q.consumers.length) tr.classList.add("reads");
      const name = el("td");
      name.append(el("span", "qname", q.description ?? slotLabel(q.slot)), el("span", "qpath", q.path));
      const v = el("td", "num");
      const vs = el("span", "value", value(q.value));
      vs.append(el("span", "unit", q.unit));
      v.append(vs);
      from(v, res, `quantities/${i}/value`);
      const sup = el("sup", "ref");
      const seen = new Set<number>();
      q.citations.forEach((c) => {
        const n = num(c);
        if (seen.has(n)) return;
        seen.add(n);
        const a = el("a", undefined, `[${n}]`);
        a.href = `#ref-${n}`;
        a.title = c.reference ?? c.id;
        a.addEventListener("click", (e) => e.stopPropagation());
        sup.append(a);
      });
      tr.append(name, v, td(q.species ? el("span", "latin", q.species) : "—"), td(confidence(q.confidence)), td(verification(q.verification)), td(sup));
      const det = el("tr", "detail");
      det.hidden = true;
      const cell = el("td");
      cell.colSpan = 6;
      const readers = q.consumers.map((c) => `${c.profile}.${c.section}.${c.field} (${c.rule})`);
      cell.append(
        dl([
          ["conditions", q.conditions],
          ["notes", q.notes],
          ["quote", q.verification.quote ? el("q", undefined, q.verification.quote) : null],
          ["read by", readers.length ? el("span", "mono", readers.join(" · ")) : "no profile reads this value yet"],
        ]),
        sourceChip(res, `quantities/${i}/value`, false),
      );
      det.append(cell);
      tr.addEventListener("click", () => {
        det.hidden = !det.hidden;
        tr.classList.toggle("open", !det.hidden);
      });
      tb.append(tr, det);
    });
    s1.body.append(wrap, el("p", "faint small", "Click a row for conditions, notes and which model parameters read it. A teal edge marks values a profile reads."));
  }
  const apply = () => {
    s1.body.querySelectorAll<HTMLTableRowElement>("tr.quantity").forEach((tr) => {
      const show = level === "all" || tr.dataset.confidence === level;
      tr.hidden = !show;
      const det = tr.nextElementSibling as HTMLTableRowElement | null;
      if (det && !show) det.hidden = true;
    });
  };
  body.append(s1.box);

  // §2 the sense
  const s2 = section("§2", "The sense");
  if (res.review_status === "draft") s2.tools.append(badge("library entry: draft", "warn", "not yet checked by a domain expert"));
  const info = res.sense_info;
  const notes = el("span", "serif");
  notes.textContent = info.notes ?? "";
  const cites = el("sup", "ref");
  info.citations.forEach((c) => {
    const n = num(c);
    const a = el("a", undefined, `[${n}]`);
    a.href = `#ref-${n}`;
    cites.append(a);
  });
  s2.body.append(
    dl([
      ["organ", info.organ ? from(el("span", undefined, info.organ), res, "sense/organ") : null],
      ["signal", info.signal ?? null],
      ["modality", info.modality ?? null],
      ["notes", info.notes ? from(notes, res, "sense/notes") : null],
      ["cited", info.citations.length ? cites : null],
    ]),
  );
  body.append(s2.box);

  // §3 open questions
  const s3 = section("§3", `Open questions`);
  s3.tools.append(el("span", "faint small", `${res.open_questions.length} in the library · ${res.requests.length} research request(s)`));
  if (!res.open_questions.length && !res.requests.length) s3.body.append(empty("None recorded."));
  else {
    const { wrap, tb } = table(["scope", "question", "status"]);
    res.open_questions.forEach((q, i) => {
      const tr = el("tr");
      tr.append(td(badge(q.scope, "muted")), td(q.text), td(el("span", "faint", "library")));
      from(tr, res, `open_questions/${i}`);
      tb.append(tr);
    });
    res.requests.forEach((r, i) => {
      const tr = el("tr");
      const q = el("td");
      q.append(r.question, " ", el("span", "qpath", r.id));
      tr.append(
        td(tags(badge(r.kind === "literal_without_rule" ? "hand-set literal" : "request", "muted"), r.priority ? badge(r.priority, r.priority === "critical" ? "alert" : r.priority === "high" ? "warn" : "muted") : null)),
        q,
        td(badge(r.status, r.status === "answered" ? "teal" : "plain")),
      );
      from(tr, res, `requests/${i}`);
      tb.append(tr);
    });
    s3.body.append(wrap);
  }
  body.append(s3.box);

  // references
  const s4 = section("", "References");
  s4.tools.append(el("span", "faint small", "profiles/library/CITATIONS.md"));
  const ol = el("ol", "refs");
  refs.forEach((c, i) => ol.append(reference(c, i + 1)));
  if (!refs.length) s4.body.append(empty("No references."));
  s4.body.append(ol);
  body.append(s4.box, inspect(res));
}
