// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Design: turn research's circuit candidates into the circuit prior learned models train on.
// §1 Candidates (research: likelihood × quality; circuits: circuitability), §2 Evidence (the
// claims and the scores behind one candidate), §3 Design (knob values bound to claims, each
// touched circuit's paper figure redrawn live, check → adopt → profile patch), §4 Designs.

import { api, type Binding, type CandidateRow, type Design, type DesignPage, type Figure, type Knob } from "../api.ts";
import { research as rs } from "../research/client.ts";
import { badge, el, empty, errorBox, inspect, link, section, srcRef, table, tags, td, toast, type Tone } from "../dom.ts";
import { day } from "../format.ts";

const LEVEL_TONE: Record<string, Tone> = { knob: "teal", circuit: "warn", new: "proposed", none: "muted" };
const STATUS_TONE: Record<string, Tone> = { draft: "plain", validated: "teal", adopted: "teal", rejected: "muted" };
const n2 = (v: number | null | undefined) => (typeof v === "number" ? v.toFixed(2) : "—");

// ---------------------------------------------------------------- figures (inline SVG)

const SVG = "http://www.w3.org/2000/svg";
function svgEl<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

/** One paper figure: its series as lines (measured solid, the paper's model dashed) and its checks. */
export function figureBox(f: Figure): HTMLElement {
  const box = el("figure", "fig design-fig");
  box.dataset.circuit = f.circuit;
  if (!f.figure) {
    box.append(el("figcaption", "faint small", `${f.circuit}: ${f.note ?? "no paper figure"}`));
    return box;
  }
  const W = 320, H = 170, L = 40, B = 26, T = 8, R = 8;
  const log = f.x?.scale === "log";
  const pts = (f.series ?? []).flatMap((s) => s.points);
  const xs = pts.map((p) => (log ? Math.log10(Math.max(p[0], 1e-12)) : p[0]));
  const ys = pts.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(0, ...ys), Math.max(...ys)];
  const sx = (x: number) => L + ((log ? Math.log10(Math.max(x, 1e-12)) : x) - x0) / (x1 - x0 || 1) * (W - L - R);
  const sy = (y: number) => H - B - (y - y0) / (y1 - y0 || 1) * (H - B - T);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": f.title ?? f.circuit, class: "plot" });
  svg.append(svgEl("line", { x1: L, y1: sy(0), x2: W - R, y2: sy(0), class: "axis" }), svgEl("line", { x1: L, y1: T, x2: L, y2: H - B, class: "axis" }));
  const lab = (x: number, y: number, text: string, anchor = "middle") => {
    const t = svgEl("text", { x, y, "text-anchor": anchor, class: "tick" });
    t.textContent = text;
    svg.append(t);
  };
  const fmt = (v: number) => (Math.abs(v) >= 100 || (Math.abs(v) < 0.01 && v !== 0) ? v.toExponential(0) : String(Math.round(v * 100) / 100));
  lab(L, H - B + 14, fmt(log ? 10 ** x0 : x0), "start");
  lab(W - R, H - B + 14, fmt(log ? 10 ** x1 : x1), "end");
  lab(L - 4, sy(y1) + 4, fmt(y1), "end");
  lab((L + W - R) / 2, H - 2, `${f.x?.label ?? ""}${f.x?.unit ? ` (${f.x.unit})` : ""}`);
  (f.series ?? []).forEach((s) => {
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
    svg.append(svgEl("path", { d, class: `series ${s.style}` }));
  });
  const legend = el("div", "legend small");
  for (const s of f.series ?? []) {
    const k = el("span", `key ${s.style}`);
    legend.append(k, el("span", undefined, s.name));
  }
  const cap = el("figcaption");
  cap.append(el("b", undefined, `${f.title ?? f.circuit}. `), el("span", "faint", f.paper ?? ""));
  const checks = el("ul", "checks small");
  for (const c of f.checks) {
    const li = el("li", c.ok ? "ok" : c.ok === false ? "bad" : "warn");
    li.append(el("b", undefined, `${c.ok ? "✓" : c.ok === false ? "✗" : "?"} ${c.name}`), ` ${c.detail}`);
    checks.append(li);
  }
  box.append(tags(badge(f.circuit, "plain"), f.ok ? badge("reproduces the paper", "teal") : badge("does not reproduce the paper", "alert")), svg, legend, cap, checks);
  return box;
}

// ---------------------------------------------------------------- the tab

interface State {
  page: DesignPage;
  selected: CandidateRow | null;
  design: Design | null; // the saved design being edited (null: a new one)
  values: Record<string, number | boolean>;
  bindings: Record<string, Binding>;
  candidateIds: string[];
  title: string;
  profile: string | null;
}

export async function designTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const page = await api.designPage(clade, sense);
  const st: State = { page, selected: null, design: null, values: {}, bindings: {}, candidateIds: [], title: "", profile: page.profiles.at(-1)?.name ?? null };
  body.replaceChildren();
  const s1 = section("§1", "Candidates from research");
  const s2 = section("§2", "Evidence");
  const s3 = section("§3", "Design");
  const s4 = section("§4", "Designs");
  body.append(s1.box, s2.box, s3.box, s4.box, inspect(page));
  renderCandidates(st, s1, () => { renderEvidence(st, s2.body); }, () => renderEditor(st, s3, s4, clade, sense));
  renderEvidence(st, s2.body);
  renderEditor(st, s3, s4, clade, sense);
}

function renderCandidates(st: State, s: ReturnType<typeof section>, onSelect: () => void, onUse: () => void): void {
  const { page } = st;
  s.tools.replaceChildren(tags(
    !page.research.configured ? badge("research not configured", "muted", "set RESEARCH_URL") : page.research.ok ? badge(`research · ${page.candidates.length} candidates`, "teal") : badge("research unreachable", "alert", page.research.error ?? ""),
    page.research.stale ? badge("scored with another circuits version", "warn", `research: ${page.research.scored_with.join(", ")}; Studio runs ${page.circuits.version ?? "?"}. Re-score to bring them in line.`) : null,
  ));
  if (page.research.configured) {
    const btn = el("button", "btn small", "Re-score");
    btn.title = "research re-scores every claim and runs senseai-circuits assess";
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await rs.refreshCandidates();
        toast(`research stored ${r.stored} candidates (${r.circuits})`);
        location.reload();
      } catch (e) {
        toast(String(e));
        btn.disabled = false;
      }
    };
    s.tools.append(btn);
  }
  s.body.replaceChildren();
  if (!page.research.configured) {
    s.body.append(empty("Research is not configured on this server (RESEARCH_URL unset), so there are no scored candidates. You can still design by hand below."));
    return;
  }
  if (page.research.error) s.body.append(el("p", "note warn", page.research.error));
  if (!page.candidates.length) {
    s.body.append(empty("Research has no circuit candidates for this sense. Re-score, or add the measurements to the library first."));
    return;
  }
  s.body.append(el("p", "faint small", "Ranked by priority = likelihood (applies to this species) × quality (of the evidence) × circuitability (what senseai-circuits can do with it). Click a row for its evidence."));
  const { wrap, tb } = table([["priority", "num"], "circuitability", "value", ["likelihood", "num"], ["quality", "num"], "measured in", "status"]);
  for (const c of page.candidates) {
    const tr = el("tr", "clickable");
    tr.dataset.candidate = c.id;
    const ca = c.circuitability;
    const what = el("td");
    what.append(el("div", "mono small", c.library_path));
    if (ca?.knob) what.append(el("div", "small", `→ ${ca.knob} = ${String(ca.value)}`));
    else if (ca) what.append(el("div", "small faint", ca.summary));
    const sp = c.score_parts?.likelihood?.species;
    const spv = sp && typeof sp === "object" ? String(sp.value ?? "") : "";
    tr.append(
      td(c.priority === null ? "—" : c.priority.toFixed(3), "num"),
      td(ca ? badge(ca.level, LEVEL_TONE[ca.level] ?? "plain", ca.summary) : badge("not checked", "muted", c.circuits_note)),
      what,
      td(n2(c.likelihood), "num"),
      td(n2(c.quality), "num"),
      td(tags(el("span", "small", c.evidence_clade), spv ? badge(spv, spv === "same species" ? "teal" : spv === "other clade" ? "warn" : "plain") : null)),
      td(badge(c.status.replace("_", " "), c.status === "adopted" ? "teal" : c.status === "rejected" ? "muted" : "plain")),
    );
    tr.onclick = () => {
      st.selected = c;
      tb.querySelectorAll("tr").forEach((r) => r.removeAttribute("aria-selected"));
      tr.setAttribute("aria-selected", "true");
      onSelect();
    };
    tb.append(tr);
  }
  s.body.append(wrap);
  const use = el("button", "btn", "Use the selected candidate in the design");
  use.dataset.testid = "use-candidate";
  use.onclick = () => {
    const c = st.selected;
    if (!c) return toast("select a candidate first");
    const ca = c.circuitability;
    if (!st.candidateIds.includes(c.id)) st.candidateIds.push(c.id);
    if (ca?.level === "knob" && ca.knob && ca.value !== null) {
      st.values[ca.knob] = ca.value;
      st.bindings[ca.knob] = { candidate_id: c.id, claim_ids: c.claim_ids };
    } else toast("this candidate sets no knob as it stands: it is linked to the design, set the value by hand");
    if (!st.title) st.title = c.library_path.split(".").slice(-1)[0].replaceAll("_", " ");
    onUse();
  };
  s.body.append(use);
}

function renderEvidence(st: State, box: HTMLElement): void {
  box.replaceChildren();
  const c = st.selected;
  if (!c) {
    box.append(empty("Select a candidate to see the claims, passages and scores behind it."));
    return;
  }
  box.append(el("p", "serif", c.mechanism));
  const grid = el("div", "grid-2");
  const left = el("div");
  const right = el("div");
  grid.append(left, right);
  box.append(grid);
  left.append(el("p", "loading small", "loading the claims…"));
  rs.candidate(c.id).then((d) => {
    left.replaceChildren();
    for (const cl of d.claims) {
      const card = el("div", "claim-card");
      card.append(tags(el("span", "mono small", cl.library_path), badge(cl.status, cl.status === "verified" ? "teal" : cl.status === "unverified" ? "warn" : "plain")));
      card.append(el("div", "value", cl.value), el("div", "small faint", [cl.species, cl.method, cl.conditions].filter(Boolean).join(" · ")));
      if (cl.passage) {
        const q = el("blockquote", "passage", cl.passage.quote);
        card.append(q, el("div", "small faint", `${cl.passage.source.authors} ${cl.passage.source.year ?? ""}, ${cl.passage.section}`));
      } else card.append(el("p", "small note warn", "No verified passage yet: nobody has found the sentence in a full-text paper."));
      for (const s of cl.sources) card.append(el("div", "small"), s.link ? link(`${s.authors} (${s.year ?? "n.d."}) ${s.title}`, s.link, true) : el("span", "small", s.title));
      left.append(card);
    }
  }).catch((e: unknown) => left.replaceChildren(errorBox(e)));

  const parts = (k: "likelihood" | "quality", total: number) => {
    const { wrap, tb } = table(["factor", "value", ["weight", "num"]]);
    for (const [name, v] of Object.entries(c.score_parts?.[k] ?? {})) {
      if (typeof v !== "object") continue;
      const tr = el("tr");
      tr.append(td(name), td(String(v.value ?? "—")), td(typeof v.weight === "number" ? v.weight.toFixed(2) : "—", "num"));
      tb.append(tr);
    }
    right.append(el("h3", undefined, `${k} ${total.toFixed(2)}`), wrap);
  };
  parts("likelihood", c.likelihood);
  parts("quality", c.quality);
  const ca = c.circuitability;
  right.append(el("h3", undefined, `circuitability ${ca ? `${ca.level} · ${ca.score}` : "not checked"}`));
  if (ca) {
    const ul = el("ul", "checks small");
    for (const ch of ca.checks) {
      const li = el("li", ch.ok ? "ok" : ch.ok === false ? "bad" : "warn");
      li.append(el("b", undefined, `${ch.ok ? "✓" : ch.ok === false ? "✗" : "?"} ${ch.name}`), ` ${ch.detail}`);
      ul.append(li);
    }
    right.append(el("p", "small", ca.summary), ul);
  } else right.append(el("p", "small faint", c.circuits_note));
  right.append(el("p", "faint small", "Weights are proposed (research docs/SPEC.md, circuits docs/DESIGN.md), shown so they can be argued with."));
}

function knobInput(k: Knob, st: State, onChange: () => void): HTMLElement {
  const cur = st.values[k.name];
  if (typeof k.default === "boolean") {
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = typeof cur === "boolean" ? cur : k.default;
    cb.onchange = () => { st.values[k.name] = cb.checked; onChange(); };
    return cb;
  }
  const inp = el("input", "num-input");
  inp.type = "number";
  inp.step = "any";
  inp.min = String(k.range[0]);
  inp.max = String(k.range[1]);
  inp.placeholder = String(k.default);
  inp.dataset.knob = k.name;
  if (typeof cur === "number") inp.value = String(cur);
  inp.oninput = () => {
    const v = inp.value.trim();
    if (v === "") {
      delete st.values[k.name];
      delete st.bindings[k.name];
    } else {
      const x = Number(v);
      inp.classList.toggle("invalid", !(x >= k.range[0] && x <= k.range[1]));
      st.values[k.name] = x;
      if (st.bindings[k.name] && st.bindings[k.name].note !== "edited") st.bindings[k.name] = { ...st.bindings[k.name], note: "edited" };
    }
    onChange();
  };
  return inp;
}

function renderEditor(st: State, s3: ReturnType<typeof section>, s4: ReturnType<typeof section>, clade: string, sense: string): void {
  const { page } = st;
  s3.tools.replaceChildren();
  s3.body.replaceChildren();
  renderDesigns(st, s4, () => renderEditor(st, s3, s4, clade, sense));
  if (!page.circuits.installed) {
    s3.body.append(empty("senseai-circuits is not installed here (SENSEAI_CIRCUITS_CMD), so knob values cannot be checked or drawn."));
    return;
  }
  const d = st.design;
  s3.tools.append(tags(d ? badge(d.status, STATUS_TONE[d.status]) : badge("new design", "plain"), d ? el("span", "mono small faint", d.id) : null));
  const locked = d?.status === "adopted" || d?.status === "rejected";

  // header: title and profile
  const head = el("div", "design-head");
  const title = el("input", "title-input");
  title.placeholder = "Design title";
  title.value = st.title;
  title.disabled = locked;
  title.oninput = () => { st.title = title.value; };
  const prof = el("select");
  prof.disabled = locked;
  prof.append(Object.assign(el("option", undefined, "— no profile —"), { value: "" }));
  for (const p of page.profiles) prof.append(Object.assign(el("option", undefined, p.name), { value: p.name, selected: p.name === st.profile }));
  prof.onchange = () => { st.profile = prof.value || null; rerenderTable(); };
  head.append(title, el("span", "faint small", "for profile"), prof);
  s3.body.append(head);
  if (!page.profiles.length) s3.body.append(el("p", "note warn", "No profile reads this sense yet: a design can be checked, but there is no profile spec to adopt it into."));

  // knob table, grouped by circuit
  const tableSlot = el("div");
  const figs = el("div", "design-figs");
  figs.dataset.testid = "design-figures";
  let timer = 0;
  let seq = 0;
  const preview = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const touched = [...new Set(Object.keys(st.values).map((k) => k.split(".")[0]))].filter((c) => ["cs", "emd", "lgmd"].includes(c));
      const mine = ++seq;
      if (!touched.length) {
        figs.replaceChildren(el("p", "faint small", "Set a knob of the retina, motion or looming circuit to see its paper figure redrawn for your values."));
        return;
      }
      figs.classList.add("busy");
      try {
        const r = await api.figures(st.values, touched);
        if (mine === seq) figs.replaceChildren(...r.figures.map(figureBox));
      } catch (e) {
        if (mine === seq) figs.replaceChildren(el("p", "note warn", String(e instanceof Error ? e.message : e)));
      } finally {
        figs.classList.remove("busy");
      }
    }, 350);
  };
  const rerenderTable = () => {
    tableSlot.replaceChildren();
    const profileValues = page.profiles.find((p) => p.name === st.profile)?.circuits ?? {};
    for (const t of page.circuit_types) {
      const mine = page.knobs.filter((k) => k.circuit === t.prefix);
      if (!mine.length) continue;
      const det = el("details", "group");
      det.open = mine.some((k) => k.name in st.values) || t.prefix === "cs";
      const sum = el("summary");
      sum.append(el("span", "gname", t.name), el("span", "faint small", t.papers), tags(t.figure ? badge("paper figure", "teal") : badge("no figure", "muted"), badge(`conserved: ${t.conserved}`, "plain")));
      const { wrap, tb } = table(["knob", "default", "profile now", "design", "evidence"]);
      for (const k of mine) {
        const tr = el("tr");
        if (k.name in st.values) tr.classList.add("reads");
        const name = el("td");
        name.append(el("span", "mono", k.name), el("div", "faint small", `${k.doc} [${k.unit}; ${k.kind}]`));
        const b = st.bindings[k.name];
        const ev = el("td");
        if (b?.claim_ids?.length) ev.append(badge(b.note === "edited" ? "claim, value edited" : "from claim", b.note === "edited" ? "warn" : "teal", b.claim_ids.join("\n")), el("div", "mono small faint", b.claim_ids[0]));
        else if (k.name in st.values) ev.append(badge("set by hand", "warn", "no claim backs this value"));
        const inpCell = el("td");
        if (locked) inpCell.append(el("span", "value", k.name in st.values ? String(st.values[k.name]) : "—"));
        else inpCell.append(knobInput(k, st, () => { tr.classList.toggle("reads", k.name in st.values); preview(); }));
        tr.append(name, td(`${String(k.default)} ${k.unit}`), td(k.name in profileValues ? String(profileValues[k.name]) : "—"), inpCell, ev);
        tb.append(tr);
      }
      det.append(sum, wrap);
      tableSlot.append(det);
    }
  };
  rerenderTable();
  s3.body.append(tableSlot, el("h3", undefined, "Paper figures for these values"), figs);
  preview();

  // last check
  if (d?.check) {
    const c = d.check;
    s3.body.append(el("h3", undefined, `Last check ${day(c.at)}: ${c.status}`));
    const ul = el("ul", "checks small");
    for (const ch of c.checks) {
      const li = el("li", ch.ok ? "ok" : ch.ok === false ? "bad" : "warn");
      li.append(el("b", undefined, `${ch.ok ? "✓" : ch.ok === false ? "✗" : "?"} ${ch.name}`), ` ${ch.detail}`);
      ul.append(li);
    }
    for (const f of c.figures) ul.append(Object.assign(el("li", f.ok ? "ok" : "bad"), { textContent: `${f.ok ? "✓" : "✗"} ${f.circuit}: ${f.title ?? ""}` }));
    s3.body.append(ul);
  }

  // adoption
  if (d?.adoption) {
    const a = d.adoption;
    s3.body.append(el("h3", undefined, `Adopted by ${a.by} ${day(a.at)}`), el("p", "serif", a.rationale), srcRef(a.spec_file), el("pre", "diff", a.diff));
    const dl = link("Download the profile patch", a.patch);
    dl.className = "btn";
    s3.body.append(dl, el("p", "faint small", "Studio does not write the profiles checkout: open this patch as a profiles PR. senseai-sdk reads the circuits: block through CircuitParams.from_profile, and learned models train on top of it."));
  }
  if (d?.research_sync?.length) {
    s3.body.append(el("p", "small faint", "Research: " + d.research_sync.map((r) => `${r.candidate_id.split(":").at(-1)} → ${r.status}${r.ok ? "" : ` (failed: ${r.error})`}`).join("; ")));
  }

  // actions
  if (locked) return;
  const bar = el("div", "card-actions");
  const msg = el("span", "small faint");
  const busy = async (fn: () => Promise<Design>, done: string) => {
    bar.querySelectorAll("button").forEach((b) => (b.disabled = true));
    msg.textContent = "working…";
    try {
      const out = await fn();
      st.design = out;
      page.designs = [out, ...page.designs.filter((x) => x.id !== out.id)];
      toast(done);
      renderEditor(st, s3, s4, clade, sense);
    } catch (e) {
      msg.textContent = String(e instanceof Error ? e.message : e);
      bar.querySelectorAll("button").forEach((b) => (b.disabled = false));
    }
  };
  const body = () => ({ title: st.title || "Untitled design", profile: st.profile, values: st.values, bindings: st.bindings, candidate_ids: st.candidateIds });
  const save = el("button", "btn", d ? "Save" : "Save draft");
  save.dataset.testid = "save-design";
  save.onclick = () => busy(() => (d ? api.updateDesign(d.id, body()) : api.createDesign(clade, sense, body())), "saved");
  const check = el("button", "btn", "Check against the papers");
  check.dataset.testid = "check-design";
  check.onclick = () => busy(async () => {
    const saved = d ? await api.updateDesign(d.id, body()) : await api.createDesign(clade, sense, body());
    return api.checkDesign(saved.id);
  }, "checked");
  bar.append(save, check);
  if (d?.status === "validated") {
    const why = el("textarea");
    why.placeholder = "Why this design should become the prior (one sentence or more)";
    why.rows = 2;
    const adopt = el("button", "btn primary", "Adopt");
    adopt.dataset.testid = "adopt-design";
    adopt.onclick = () => busy(() => api.adoptDesign(d.id, why.value), "adopted: the profile patch is ready");
    const reject = el("button", "btn", "Reject");
    reject.onclick = () => busy(() => api.rejectDesign(d.id, why.value), "rejected");
    s3.body.append(why);
    bar.append(adopt, reject);
  }
  bar.append(msg);
  s3.body.append(bar);
}

function renderDesigns(st: State, s4: ReturnType<typeof section>, open: () => void): void {
  s4.body.replaceChildren();
  const { page } = st;
  if (!page.designs.length) {
    s4.body.append(empty("No designs for this sense yet."));
    return;
  }
  const { wrap, tb } = table(["design", "status", "profile", "knobs", "updated"]);
  for (const d of page.designs) {
    const tr = el("tr", "clickable");
    tr.dataset.design = d.id;
    if (st.design?.id === d.id) tr.setAttribute("aria-selected", "true");
    const name = el("td");
    name.append(el("div", undefined, d.title), el("div", "mono small faint", d.id));
    tr.append(name, td(badge(d.status, STATUS_TONE[d.status])), td(el("span", "mono small", d.profile ?? "—")), td(el("span", "mono small", Object.entries(d.values).map(([k, v]) => `${k}=${String(v)}`).join(", "))), td(day(d.updated_at)));
    tr.onclick = () => {
      st.design = d;
      st.values = { ...d.values };
      st.bindings = { ...d.bindings };
      st.candidateIds = [...d.candidate_ids];
      st.title = d.title;
      st.profile = d.profile;
      open();
    };
    tb.append(tr);
  }
  const fresh = el("button", "btn small", "New design");
  fresh.onclick = () => {
    Object.assign(st, { design: null, values: {}, bindings: {}, candidateIds: [], title: "" });
    open();
  };
  s4.tools.replaceChildren(fresh);
  s4.body.append(wrap);
}
