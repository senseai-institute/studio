// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Model: what has been built from the sources, in four blocks: circuits (and the profile rules
// that set head priors), world prior, learned networks, reflex.

import { api, type Model, type SpecField } from "../api.ts";
import { badge, el, empty, from, inspect, panel, sourceChip } from "../dom.ts";
import { short, value } from "../format.ts";

function fieldRow(res: Model, f: SpecField, field: string): HTMLElement {
  const tr = el("tr");
  tr.append(el("td", "mono", `${f.section}.${f.field}`));
  const what = el("td");
  if (f.kind === "rule") {
    what.append(el("span", "mono", f.rule ?? ""), " ");
    const paths = Object.values(f.library_paths ?? {});
    if (paths.length) what.append(badge("species", "teal", `reads ${paths.join(", ")}`));
    else what.append(badge("hand-set arguments", "warn", "a rule with only literal arguments"));
    if (f.rationale) what.append(el("div", "muted small", f.rationale));
    if (paths.length) what.append(el("div", "mono small", paths.join(" · ")));
  } else {
    what.append(badge("hand-set literal", "warn", "a design choice, not read from the library"));
  }
  const val = el("td", "mono");
  if (f.kind === "literal") val.textContent = typeof f.literal === "object" ? JSON.stringify(f.literal) : String(f.literal);
  else if (typeof f.value === "number") val.textContent = value(Math.round(f.value * 1000) / 1000);
  else if (f.value_error) val.append(badge("not computed", "alert", f.value_error));
  else val.append(el("span", "muted", f.output === "gain_lut" || f.output === "attention" ? "curve (needs the sensor spec)" : "computed at load"));
  tr.append(what, val);
  from(tr, res, field);
  if (f.reads_this_sense) tr.classList.add("reads");
  return tr;
}

function table(head: string[]): { t: HTMLTableElement; tb: HTMLTableSectionElement } {
  const t = el("table", "grid");
  const th = el("thead");
  const tr = el("tr");
  head.forEach((h) => tr.append(el("th", undefined, h)));
  th.append(tr);
  const tb = el("tbody");
  t.append(th, tb);
  return { t, tb };
}

export async function modelTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const res = await api.model(clade, sense);
  body.replaceChildren();
  if (res.engine !== "senseai-profiles") body.append(el("p", "note warn", `Profile specs read as plain YAML: ${res.engine_error ?? "senseai-profiles did not run"}. Rule values are not computed.`));

  // ---- circuits + profile rules
  const c = panel("Circuits");
  c.head.append(res.circuits.installed ? badge("circuits installed", "teal") : badge("circuits: not installed", "muted"));
  if (res.circuits.installed && !res.circuits.ok) c.body.append(el("p", "error", res.circuits.error ?? "senseai-circuits failed"));
  if (res.circuits.knobs.length) {
    const { t, tb } = table(["knob", "value", "kind", "set by", "rule status"]);
    res.circuits.knobs.forEach((k, i) => {
      const tr = el("tr");
      const kind = String(k.kind ?? "");
      tr.append(
        el("td", "mono", String(k.knob ?? k.name ?? "")),
        el("td", "mono", `${value(k.value)} ${String(k.unit ?? "")}`),
        el("td"),
        el("td", "mono", String(k.rule ?? "")),
        el("td", undefined, String(k.status ?? k.rule_status ?? "")),
      );
      tr.children[2].append(badge(kind === "circuit" ? "circuit value, not species" : kind || "?", kind === "species" ? "teal" : kind === "circuit" ? "warn" : "muted"));
      from(tr, res, `circuits/knobs/${i}`);
      tb.append(tr);
    });
    c.body.append(t);
  } else {
    c.body.append(empty(res.circuits.installed ? "No circuit knob is set for this sense yet." : "No circuit knob is set for this sense yet (senseai-circuits is not installed here)."));
  }
  if (res.rulebook.present) {
    const ul = el("ul", "rules");
    res.rulebook.rules.forEach((r, i) => {
      const li = el("li");
      li.append(el("span", "mono", String(r.id)), " sets ", el("span", "mono", String(r.sets ?? "—")), " ", badge(String(r.status ?? "no status"), r.status === "accepted" ? "teal" : "warn"));
      from(li, res, `rulebook/rules/${i}`);
      ul.append(li);
    });
    c.body.append(el("h3", undefined, "Rulebook"), res.rulebook.rules.length ? ul : empty("No rulebook rule names this sense yet."));
  } else {
    c.body.append(el("p", "muted small", "No rulebook in this profiles checkout yet."));
  }
  body.append(c.box);

  const p = panel("Profile rules (head priors and reflex)");
  if (!res.profiles.length) p.body.append(empty("No profile reads this sense yet: nothing has been built from these sources."));
  res.profiles.forEach((pr, pi) => {
    const box = el("div", "profile");
    const h = el("h3");
    h.append(el("span", "mono", pr.name), " ");
    if (pr.control) h.append(badge("control", "muted"));
    if (pr.spec_hash) h.append(badge(`spec ${short(pr.spec_hash)}`, "muted", pr.spec_hash));
    h.append(pr.bundles?.length ? badge(`prior bundle v${pr.bundles.join(", v")}`, "teal") : badge("no prior bundle", "warn", "run senseai-profiles distill"));
    box.append(h);
    if (pr.description) box.append(el("p", "muted", pr.description));
    const { t, tb } = table(["field", "what sets it", "value"]);
    pr.fields.forEach((f, fi) => tb.append(fieldRow(res, f, `profiles/${pi}/fields/${fi}`)));
    box.append(t, el("span", "src mono", pr.source_file));
    p.body.append(box);
  });
  body.append(p.box);

  // ---- world prior
  const w = panel("World prior");
  if (!res.world_prior.ok) {
    w.head.append(badge("world: not found", "muted"));
    w.body.append(el("p", "muted", res.world_prior.error ?? ""));
  } else {
    const counts = new Map<string, number>();
    res.world_prior.params.forEach((x) => counts.set(x.kind, (counts.get(x.kind) ?? 0) + 1));
    for (const [k, n] of counts) w.head.append(badge(`${n} ${k}`, k === "measured" ? "teal" : k === "proposed" ? "warn" : "muted"));
    const { t, tb } = table(["parameter", "value", "kind", "source"]);
    res.world_prior.params.forEach((x, i) => {
      const tr = el("tr");
      const kind = el("td");
      kind.append(badge(x.kind, x.kind === "measured" ? "teal" : x.kind === "proposed" ? "warn" : "muted", x.kind === "proposed" ? "a flagged placeholder: the literature describes it, the library has not verified it" : ""));
      tr.append(el("td", "mono", x.name), el("td", "mono", value(x.value)), kind, el("td", "small", x.source));
      if (x.reads_this_sense) tr.classList.add("reads");
      from(tr, res, `world_prior/params/${i}`);
      tb.append(tr);
    });
    w.body.append(el("p", "muted small", `Structured prior built from ${res.world_prior.library}. Highlighted rows read this sense.`), t);
  }
  body.append(w.box);

  // ---- learned networks
  const l = panel("Learned networks");
  if (!res.learned.length) {
    l.head.append(badge("untrained", "warn"));
    l.body.append(empty("None: untrained. No world checkpoint is configured (SENSEAI_WORLD_CKPT) or found in the artefact store."));
  }
  res.learned.forEach((n, i) => {
    const row = el("div", "learned");
    row.append(el("div", "mono", n.path));
    if (!n.ok) row.append(badge("unreadable", "alert", n.error ?? ""), el("p", "muted small", n.error ?? ""));
    else {
      row.append(
        badge(n.params_total ? `${(n.params_total / 1e6).toFixed(1)} M params` : "params unknown", "teal"),
        " ",
        badge(`model ${short(n.model_id)}`, "muted"),
        " ",
        badge(n.step ? `step ${n.step}` : "step ?", "muted"),
      );
      row.append(el("p", "small", `tokenizer: ${n.tokenizer ? JSON.stringify(n.tokenizer) : "not recorded"} · training data: ${n.training_data ? JSON.stringify(n.training_data) : "not recorded"}`));
    }
    row.append(sourceChip(res, `learned/${i}`));
    l.body.append(row);
  });
  body.append(l.box);

  // ---- reflex
  const r = panel("Reflex");
  if (!res.reflex.length) r.body.append(empty("No reflex setting reads this sense yet."));
  res.reflex.forEach((rf) => {
    const box = el("div", "profile");
    box.append(el("h3", "mono", rf.profile));
    for (const f of rf.fields) {
      const line = el("p");
      line.append(el("span", "mono", f.field), ": ");
      if (f.kind === "rule") {
        line.append(el("b", "mono", typeof f.value === "number" ? value(Math.round(f.value * 1000) / 1000) : "—"), " ", badge(`rule ${f.rule}`, "teal", f.rationale ?? ""), " ", el("span", "mono small", Object.values(f.library_paths ?? {}).join(", ")));
      } else {
        line.append(el("b", "mono", typeof f.literal === "object" ? JSON.stringify(f.literal) : String(f.literal)), " ", badge("hand-set literal", "warn"));
      }
      box.append(line);
    }
    box.append(el("p", "muted small", "commit_threshold is the fraction of the evidence window spent before committing; the reflex threshold θ it implies is computed by senseai-reflex at load."), el("span", "src mono", rf.source_file));
    r.body.append(box);
  });
  body.append(r.box, inspect(res));
}
