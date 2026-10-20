// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Home: the atlas. Totals across the library, then a species × modality matrix: one row per
// library entry, one column per modality the library describes, a cell per sense with its
// state, counts and pipeline progress. Everything comes from /api/studio/species.

import type { Card, Chip, Species } from "../api.ts";
import { badge, el, errorBox, from, inspect, section, table } from "../dom.ts";
import { step } from "../format.ts";
import { shell, species } from "../shell.ts";

function stat(v: number | string, k: string, dot?: string): HTMLElement {
  const s = el("div", "stat");
  const label = el("div", "k");
  if (dot) label.append(el("span", `dot ${dot}`));
  label.append(k);
  s.append(el("div", "v", String(v)), label);
  return s;
}

function cell(res: Species, c: Card, ci: number, s: Chip): HTMLElement {
  const si = c.senses.indexOf(s);
  const a = el("a", `cell state-${s.state}`);
  a.href = `/studio/${encodeURIComponent(c.clade)}/${encodeURIComponent(s.id)}`;
  a.dataset.sense = s.id;
  const top = el("div", "top");
  top.append(el("span", `dot ${s.state}`), s.id, el("span", "state", s.state));
  const nums = el("div", "nums");
  nums.append(el("span", undefined, `${s.values} val`), el("span", undefined, `${s.sources} src`), el("span", undefined, `${s.open_questions} open`));
  const mini = el("div", "mini");
  for (let i = 1; i <= s.steps; i++) {
    const it = el("i");
    if (i < s.step || (s.complete && i === s.step)) it.className = "done";
    else if (i === s.step) it.className = "current";
    mini.append(it);
  }
  mini.title = step(s.step, s.steps);
  a.append(top, nums, mini);
  a.title = [
    s.profiles.length ? `read by ${s.profiles.join(", ")}` : s.state === "described" ? "cited values; no profile reads them yet" : "no cited value yet",
    s.data === "available" ? `${s.recordings} recording(s)` : s.data === "synthetic" ? "synthetic data only" : "no data stream",
    step(s.step, s.steps),
  ].join(" · ");
  from(a, res, `cards/${ci}/senses/${si}/state`);
  return a;
}

export async function homePage(root: HTMLElement): Promise<void> {
  const { page } = await shell(root, [["Atlas", null]]);
  let res: Species;
  try {
    res = await species();
  } catch (e) {
    page.append(errorBox(e));
    return;
  }
  const intro = el("header");
  intro.style.display = "grid";
  intro.style.gap = "8px";
  intro.append(
    el("div", "eyebrow", "Species Sensory Library · SenseAI"),
    el("h1", "page-title", "Atlas of species senses"),
    el("p", "lede", "Each cell is one sense of one species: the cited values it rests on, whether a model reads it, and how far it is through the ten-step pipeline. Open a cell to read the sources, inspect the model, and run it."),
  );
  const t = res.totals;
  const stats = el("div", "stats");
  stats.append(
    stat(t.clades, "species entries"),
    stat(t.senses, "senses"),
    stat(t.modelled, "modelled", "modelled"),
    stat(t.described, "described", "described"),
    stat(t.empty, "empty", "empty"),
    stat(t.values, "cited values"),
    stat(t.references, "references"),
    stat(t.open_questions, "open questions"),
  );
  page.append(intro, stats);
  if (res.engine !== "senseai-profiles") page.append(el("p", "note warn", `Profile specs were read as plain YAML (${res.engine}): the checkout's senseai-profiles code did not run, so rule values are not computed.`));

  const mods = res.modalities;
  const s = section("", "Species × modality");
  s.tools.append(el("span", "faint small", "modalities as the library's schema names them"));
  const { wrap, t: tbl, tb } = table(["species", ...mods]);
  tbl.classList.add("atlas");
  res.cards.forEach((c, ci) => {
    const tr = el("tr");
    tr.dataset.clade = c.clade;
    const name = el("td", "clade-cell");
    const cn = el("div", "cname", c.names[0] ?? c.clade);
    from(cn, res, `cards/${ci}/names`);
    const lat = el("div");
    lat.append(el("span", "latin", c.latin ?? c.clade), " ", c.review_status === "draft" ? badge("draft", "warn", "library entry not yet checked by a domain expert") : badge("reviewed", "teal"));
    const rep = c.representative.map((r) => (r.common_name ? `${r.common_name} (${r.name})` : r.name)).join("; ");
    name.append(cn, lat);
    if (rep) name.append(from(el("div", "rep", rep), res, `cards/${ci}/representative`));
    tr.append(name);
    for (const m of mods) {
      const td = el("td");
      const here = c.senses.filter((x) => x.modality === m);
      if (!here.length) td.append(el("div", "cell-none", "—"));
      for (const x of here) td.append(cell(res, c, ci, x));
      tr.append(td);
    }
    tb.append(tr);
  });
  s.body.append(wrap);
  if (!res.cards.length) s.body.append(el("p", "empty", "No library entries found. Set SENSEAI_PROFILES_REPO to a profiles checkout."));
  page.append(s.box, inspect(res));
}
