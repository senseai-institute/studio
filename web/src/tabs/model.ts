// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Model: what has been built from the sources. Fig. 1 traces cited values to parameters; then
// circuits (the senseai-circuits knob registry, species value or circuit default), head priors
// (profile rules), the world prior, learned networks and the reflex.

import { api, type Knob, type SpecField } from "../api.ts";
import { badge, el, empty, from, inspect, kindTag, section, sourceChip, srcRef, table, tags, td } from "../dom.ts";
import { short, value } from "../format.ts";
import { lineageData, lineageSvg } from "../lineage.ts";

function fieldValue(f: SpecField): HTMLElement {
  const v = el("span", "value");
  if (f.kind === "literal") v.textContent = typeof f.literal === "object" ? JSON.stringify(f.literal) : String(f.literal);
  else if (typeof f.value === "number") v.textContent = value(Math.round(f.value * 1000) / 1000);
  else if (f.value_error) v.append(badge("not computed", "alert", f.value_error));
  else v.append(el("span", "faint", f.output === "gain_lut" || f.output === "attention" ? "curve over lux · needs the sensor spec" : "computed at load"));
  return v;
}

function knobValue(k: Knob): HTMLElement {
  const cell = el("div");
  const sv = k.species_values;
  if (sv.length) {
    for (const s of sv) {
      const line = el("div");
      line.append(el("span", "value", String(s.value)), el("span", "unit faint", ` ${k.unit}`), " ", badge(`species · ${s.profile}`, "teal", "set by the species file"));
      cell.append(line, srcRef(`${s.source_file}${typeof s.line === "number" ? `:${s.line}` : ` · ${s.line}`}`, true));
    }
    const d = el("div", "faint small", `circuit default ${String(k.default)} ${k.unit}`);
    cell.append(d);
  } else {
    const line = el("div");
    line.append(el("span", "value", String(k.default)), el("span", "unit faint", ` ${k.unit}`));
    const d = el("div", "faint small", "circuit default");
    d.title = "this species file does not set this knob; the circuit's registry default applies (circuit value, not species)";
    cell.append(line, d);
  }
  return cell;
}

export async function modelTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const [res, src] = await Promise.all([api.model(clade, sense), api.sources(clade, sense).catch(() => null)]);
  body.replaceChildren();
  if (res.engine !== "senseai-profiles") body.append(el("p", "note warn", `Profile specs were read as plain YAML: ${res.engine_error ?? "senseai-profiles did not run"}. Rule values are not computed.`));

  // Fig. 1
  const data = src ? lineageData(res, src) : null;
  const s0 = section("Fig. 1", "From cited values to model parameters");
  if (data) {
    const fig = el("figure", "fig");
    const wrap = el("div", "lineage");
    wrap.append(lineageSvg(data));
    const cap = el("figcaption");
    cap.append(el("b", undefined, "Fig. 1. "), `Every model parameter that reads this sense, traced to the library value it comes from. Solid: a profile rule (computed values on the right). Dashed: the structured world prior, which reads the library through PriorParams.from_library. Parameters set by hand appear in §3, not here.`);
    fig.append(wrap, cap);
    s0.body.append(fig);
  } else {
    s0.body.append(empty("Nothing in the model reads this sense yet. Its cited values are described in the library but no rule turns them into a parameter."));
  }
  body.append(s0.box);

  // §1 circuits
  const c = res.circuits;
  const s1 = section("§1", "Circuits");
  s1.tools.append(tags(
    c.installed ? (c.ok ? badge(`senseai-circuits · ${c.knobs.length} knobs`, "teal") : badge("senseai-circuits failed", "alert", c.error ?? "")) : badge("circuits: not installed", "muted", "set SENSEAI_CIRCUITS_CMD or install senseai-circuits"),
    c.knobs.length ? badge(`${c.species_set} of ${c.knobs.length} set by the species`, c.species_set ? "teal" : "warn", "knobs the species file sets; the rest run on circuit defaults") : null,
  ));
  if (!c.installed) {
    s1.body.append(empty("senseai-circuits is not installed here, so its knob registry cannot be shown. The circuits this sense would use are listed below."));
    if (c.groups.length) s1.body.append(el("p", "small faint", c.groups.map((g) => g.name).join(" · ")));
  } else if (!c.ok) s1.body.append(el("p", "note alert", c.error ?? "senseai-circuits knobs --json failed"));
  else if (!c.knobs.length) s1.body.append(empty("No circuit serves this modality yet."));
  else {
    for (const g of c.groups) {
      const mine = c.knobs.map((k, i) => [k, i] as const).filter(([k]) => k.circuit === g.prefix);
      const det = el("details", "group");
      det.dataset.circuit = g.prefix;
      const sum = el("summary");
      const kinds = new Map<string, number>();
      mine.forEach(([k]) => kinds.set(k.kind, (kinds.get(k.kind) ?? 0) + 1));
      const set = mine.filter(([k]) => k.species_values.length).length;
      sum.append(
        el("span", "gname", g.name),
        el("span", "faint mono small", `${g.prefix}.* · ${mine.length} knobs`),
        tags(...[...kinds].map(([k, n]) => badge(`${n} ${k}`, k === "measured" ? "measured" : k === "proposed" ? "proposed" : "physics")), badge(set ? `${set} set by species` : "all circuit defaults", set ? "teal" : "muted")),
      );
      const { wrap, tb } = table(["knob", "value", "range", "kind", "basis"]);
      for (const [k, i] of mine) {
        const tr = el("tr");
        if (k.species_values.length) tr.classList.add("reads");
        const name = el("td");
        name.append(el("span", "mono", k.name), el("div", "faint small", k.doc));
        tr.append(name, td(knobValue(k)), td(el("span", "value", `[${k.range[0]}, ${k.range[1]}]`)), td(kindTag(k.kind)), td(el("span", "small", k.source)));
        from(tr, res, `circuits/knobs/${i}`);
        tb.append(tr);
      }
      det.append(sum, wrap);
      s1.body.append(det);
    }
    s1.body.append(el("p", "faint small", "Kinds come from the circuits registry: measured values may come from another species (e.g. fly or locust); “species” marks a value this species file sets."));
  }
  if (res.rulebook.present) {
    const h = el("h3", undefined, "Rulebook");
    s1.body.append(h);
    if (!res.rulebook.rules.length) s1.body.append(empty("No rulebook rule names this sense yet."));
    else {
      const { wrap, tb } = table(["rule", "sets", "status", "reads"]);
      res.rulebook.rules.forEach((r, i) => {
        const tr = el("tr");
        tr.append(td(el("span", "mono", String(r.id))), td(el("span", "mono", String(r.sets ?? "—"))), td(badge(String(r.status ?? "no status"), r.status === "accepted" ? "teal" : "warn")), td(el("span", "mono small", r.reads.join(", "))));
        from(tr, res, `rulebook/rules/${i}`);
        tb.append(tr);
      });
      s1.body.append(wrap);
    }
  } else s1.body.append(el("p", "faint small", "No rulebook in this profiles checkout yet."));
  body.append(s1.box);

  // §2 head priors
  const s2 = section("§2", "Head priors (profile rules)");
  if (!res.profiles.length) s2.body.append(empty("No profile reads this sense yet: nothing has been built from these sources."));
  res.profiles.forEach((pr, pi) => {
    const h = el("h3");
    h.append(el("span", "mono", pr.name), tags(pr.control ? badge("control", "muted") : null, pr.spec_hash ? badge(`spec ${short(pr.spec_hash, 10)}`, "plain", pr.spec_hash) : null, pr.bundles?.length ? badge(`prior bundle v${pr.bundles.join(", v")}`, "teal") : badge("no prior bundle", "warn", "run senseai-profiles distill")));
    s2.body.append(h);
    if (pr.description) s2.body.append(el("p", "muted serif", pr.description));
    const { wrap, tb } = table(["field", "set by", "value"]);
    pr.fields.forEach((f, fi) => {
      if (f.section === "reflex") return;
      const tr = el("tr");
      if (f.reads_this_sense) tr.classList.add("reads");
      const how = el("td");
      if (f.kind === "rule") {
        const paths = Object.values(f.library_paths ?? {});
        how.append(el("span", "mono", `rule ${f.rule}`), " ", paths.length ? badge("species", "teal", `reads ${paths.join(", ")}`) : badge("hand-set arguments", "warn", "a rule with only literal arguments"));
        if (f.rationale) how.append(el("div", "faint small", f.rationale));
        if (paths.length) how.append(el("div", "qpath", paths.join(" · ")));
      } else how.append(badge("hand-set literal", "warn", "a design choice, not read from the library"));
      tr.append(td(el("span", "mono", `${f.section}.${f.field}`)), how, td(fieldValue(f)));
      from(tr, res, `profiles/${pi}/fields/${fi}`);
      tb.append(tr);
    });
    s2.body.append(wrap, srcRef(pr.source_file, true));
  });
  body.append(s2.box);

  // §3 world prior
  const s3 = section("§3", "World prior (structured, no training)");
  if (!res.world_prior.ok) {
    s3.tools.append(badge("senseai-world not found", "muted"));
    s3.body.append(el("p", "faint", res.world_prior.error ?? ""));
  } else {
    const counts = new Map<string, number>();
    res.world_prior.params.forEach((x) => counts.set(x.kind, (counts.get(x.kind) ?? 0) + 1));
    for (const [k, n] of counts) s3.tools.append(badge(`${n} ${k}`, k === "measured" ? "measured" : k === "proposed" ? "proposed" : "physics"));
    const { wrap, tb } = table(["parameter", ["value", "num"], "kind", "source"]);
    res.world_prior.params.forEach((x, i) => {
      const tr = el("tr");
      if (x.reads_this_sense) tr.classList.add("reads");
      tr.append(td(el("span", "mono", x.name)), td(value(x.value), "num"), td(kindTag(x.kind)), td(el("span", "small", x.source)));
      from(tr, res, `world_prior/params/${i}`);
      tb.append(tr);
    });
    s3.body.append(el("p", "faint small", `PriorParams.from_library(${res.world_prior.library}). A teal edge marks parameters read from this sense.`), wrap);
  }
  body.append(s3.box);

  // §4 learned
  const s4 = section("§4", "Learned networks");
  if (!res.learned.length) {
    s4.tools.append(badge("untrained", "warn"));
    s4.body.append(empty("None: untrained. No world checkpoint is configured (SENSEAI_WORLD_CKPT) or found in the artefact store."));
  } else {
    const { wrap, tb } = table(["checkpoint", ["parameters", "num"], "model", "tokenizer / training data"]);
    res.learned.forEach((n, i) => {
      const tr = el("tr");
      const name = el("td");
      name.append(el("span", "mono small", n.path), sourceChip(res, `learned/${i}`));
      if (!n.ok) {
        const e = el("td");
        e.colSpan = 3;
        e.append(badge("unreadable", "alert"), " ", n.error ?? "");
        tr.append(name, e);
      } else {
        tr.append(
          name,
          td(n.params_total ? `${(n.params_total / 1e6).toFixed(2)} M` : "—", "num"),
          td(el("span", "mono", `${short(n.model_id)} · step ${n.step ?? "?"}`)),
          td(el("span", "small", `${n.tokenizer ? JSON.stringify(n.tokenizer) : "tokenizer not recorded"} · ${n.training_data ? JSON.stringify(n.training_data) : "training data not recorded"}`)),
        );
      }
      tb.append(tr);
    });
    s4.body.append(wrap);
  }
  body.append(s4.box);

  // §5 reflex
  const s5 = section("§5", "Reflex");
  if (!res.reflex.length) s5.body.append(empty("No reflex setting reads this sense yet."));
  else {
    const { wrap, tb } = table(["profile", "field", "set by", "value"]);
    for (const rf of res.reflex) {
      for (const f of rf.fields) {
        const how = el("td");
        if (f.kind === "rule") how.append(el("span", "mono", `rule ${f.rule}`), " ", badge("species", "teal", f.rationale ?? ""), el("div", "qpath", Object.values(f.library_paths ?? {}).join(", ")));
        else how.append(badge("hand-set literal", "warn"));
        const tr = el("tr");
        tb.append(tr);
        tr.append(td(el("span", "mono", rf.profile)), td(el("span", "mono", f.field)), how, td(fieldValue(f)));
      }
    }
    s5.body.append(wrap, el("p", "faint small", "commit_threshold is the fraction of the evidence window spent before committing; the reflex threshold θ it implies is computed by senseai-reflex at load."));
  }
  body.append(s5.box, inspect(res));
}
