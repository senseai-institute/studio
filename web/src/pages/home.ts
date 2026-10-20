// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Home: one card per library entry, a chip per sense. Chip state and badges come from the API.

import { api, type Card, type Species } from "../api.ts";
import { topbar } from "../chrome.ts";
import { badge, el, errorBox, from, inspect } from "../dom.ts";
import { dataLabel, step } from "../format.ts";

function card(res: Species, c: Card, ci: number): HTMLElement {
  const box = el("article", "species-card");
  box.dataset.clade = c.clade;
  const head = el("header");
  const name = el("h2", undefined, c.names[0] ?? c.clade);
  from(name, res, `cards/${ci}/names`);
  const latin = el("span", "latin", c.latin ?? c.clade);
  from(latin, res, `cards/${ci}/latin`);
  head.append(name, latin);
  box.append(head);
  const rep = c.representative.map((r) => (r.common_name ? `${r.common_name} (${r.name})` : r.name)).join(", ");
  if (rep) box.append(from(el("p", "rep", rep), res, `cards/${ci}/representative`));
  if (c.niche) box.append(from(el("p", "niche", c.niche), res, `cards/${ci}/niche`));

  const chips = el("div", "chips");
  chips.setAttribute("aria-label", "Senses");
  c.senses.forEach((s, si) => {
    const a = el("a", `chip state-${s.state}`);
    a.href = `/studio/${encodeURIComponent(c.clade)}/${encodeURIComponent(s.id)}`;
    a.dataset.sense = s.id;
    a.append(el("span", "chip-name", s.id), el("span", "chip-state", s.state));
    from(a, res, `cards/${ci}/senses/${si}/state`);
    const tip = [
      `${s.state}: ${s.profiles.length ? `read by ${s.profiles.join(", ")}` : s.state === "described" ? "cited values, no profile reads them" : "no cited value yet"}`,
      dataLabel(s.data),
      step(s.step, s.steps),
    ];
    a.title = `${tip.join(" · ")}\n${a.title}`;
    chips.append(a);
  });
  box.append(chips);

  const badges = el("div", "badges");
  const tone = c.data === "available" ? "teal" : c.data === "synthetic" ? "warn" : "muted";
  badges.append(badge(dataLabel(c.data), tone));
  if (c.step !== null) badges.append(badge(`pipeline ${step(c.step, c.steps)}`, "muted", "furthest sense; open a sense for its steps"));
  if (c.review_status === "draft") badges.append(badge("library: draft", "warn", "not yet checked by a domain expert"));
  box.append(badges);
  return box;
}

export async function homePage(root: HTMLElement): Promise<void> {
  const main = el("main", "home");
  root.replaceChildren(topbar("Species × sense"), main);
  let res: Species;
  try {
    res = await api.species();
  } catch (e) {
    main.append(errorBox(e));
    return;
  }
  const intro = el("p", "intro muted");
  intro.textContent = "Pick a species and a sense to see its sources, what has been built from them, run it, and where it is in the pipeline.";
  const legend = el("div", "legend chips-legend");
  for (const s of ["modelled", "described", "empty"]) {
    const i = el("span", `chip state-${s} mini`, s);
    legend.append(i);
  }
  legend.append(el("span", "muted", "modelled: a profile reads it · described: cited values only · empty: nothing cited yet"));
  main.append(intro, legend);
  if (res.engine !== "senseai-profiles") {
    main.append(el("p", "note warn", `Profile specs read as plain YAML (${res.engine}): the senseai-profiles code in the checkout did not run, so rule values are not computed.`));
  }
  const grid = el("div", "species-grid");
  res.cards.forEach((c, i) => grid.append(card(res, c, i)));
  if (!res.cards.length) grid.append(el("p", "empty muted", "No library entries found. Set SENSEAI_PROFILES_REPO to a profiles checkout."));
  main.append(grid, inspect(res));
}
