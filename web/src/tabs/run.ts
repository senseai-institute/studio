// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Run: pick a data source and arms, press Run, watch it live, then read the side-by-side. Every
// option the server cannot run stays visible with the reason; banners say what a run is not.

import { api, type Job, type RunOptions } from "../api.ts";
import { badge, el, empty, inspect, panel } from "../dom.ts";
import { day, ms, pct } from "../format.ts";
import { liveView, type Live } from "../live.ts";

function banners(job: Job | null, opts: RunOptions, sourceSynthetic: boolean, preregistered: boolean): HTMLElement {
  const b = el("div", "banners");
  if (sourceSynthetic) b.append(el("p", "banner warn", "Synthetic data: shows the pipeline, not a result."));
  if (!preregistered) b.append(el("p", "banner muted", "Not pre-registered: an exploratory run, not evidence for a claim."));
  if (job?.arms.some((a) => a.world === "prior")) b.append(el("p", "banner muted", "World: structured prior (no training)."));
  if (opts.arms.every((a) => a.role !== "species")) b.append(el("p", "banner muted", "No profile reads this sense yet: only the control runs."));
  return b;
}

function summaryTable(job: Job): HTMLElement {
  const t = el("table", "grid side-by-side");
  const head = el("tr");
  ["arm", "sequence", "caught", "median delay", "false fires / h", "latency p50", "latency p99"].forEach((h) => head.append(el("th", undefined, h)));
  const th = el("thead");
  th.append(head);
  const tb = el("tbody");
  for (const s of job.summaries) {
    const tr = el("tr");
    const err = s.error ? String(s.error) : null;
    tr.append(el("td", "mono", job.arms.find((a) => a.bench_arm === s.arm)?.id ?? String(s.arm ?? "")), el("td", "mono", String(s.sequence ?? "")));
    if (err) {
      const td = el("td", "error", err);
      td.colSpan = 5;
      tr.append(td);
    } else {
      tr.append(
        el("td", "mono", s.hit_rate === null || s.hit_rate === undefined ? "— (no labels)" : pct(s.hit_rate)),
        el("td", "mono", typeof s.median_delay_s === "number" ? `${s.median_delay_s.toFixed(2)} s` : "—"),
        el("td", "mono", typeof s.unattributed_fires_per_h === "number" ? s.unattributed_fires_per_h.toFixed(1) : "—"),
        el("td", "mono", ms(s.latency_p50_ms)),
        el("td", "mono", ms(s.latency_p99_ms)),
      );
    }
    tb.append(tr);
  }
  t.append(th, tb);
  return t;
}

export async function runTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const [opts, recent] = await Promise.all([api.runOptions(clade, sense), api.jobs(clade, sense).catch(() => [] as Job[])]);
  body.replaceChildren();
  const form = panel("Run in real time");
  if (!opts.bench.found) form.head.append(badge("senseai-bench not found", "alert", opts.bench.error ?? ""));
  const bannerSlot = el("div");
  form.body.append(bannerSlot);

  // sources
  const srcBox = el("fieldset", "choices");
  srcBox.append(el("legend", undefined, "Data"));
  if (!opts.sources.length) srcBox.append(empty(`No data for this sense yet: no stream is defined for the ${opts.modality} modality.`));
  let source: string | null = null;
  for (const s of opts.sources) {
    const lab = el("label", s.available ? "" : "off");
    const r = el("input");
    r.type = "radio";
    r.name = "source";
    r.value = s.id;
    r.disabled = !s.available;
    if (s.available && source === null) {
      r.checked = true;
      source = s.id;
    }
    r.addEventListener("change", () => {
      source = s.id;
      update();
    });
    lab.append(r, " ", s.synthetic ? `Synthetic (${(s.streams ?? []).join(" + ").toLowerCase()})` : `${s.dataset} · ${s.name}`, " ");
    if (s.synthetic) lab.append(badge("synthetic", "warn"));
    else lab.append(badge(s.labelled ? "labelled" : "no labels", s.labelled ? "teal" : "muted"));
    if (!s.available) lab.append(el("span", "reason", s.reason));
    srcBox.append(lab);
  }
  if (opts.sources.length && opts.sources.every((s) => s.synthetic)) srcBox.append(el("p", "muted small", "No recordings for this sense under SENSEAI_DATA_ROOT yet: synthetic only."));

  // arms
  const armBox = el("fieldset", "choices");
  armBox.append(el("legend", undefined, "Arms"));
  const picked = new Set<string>();
  for (const a of opts.arms) {
    const lab = el("label", a.available ? "" : "off");
    const c = el("input");
    c.type = "checkbox";
    c.value = a.id;
    c.disabled = !a.available;
    if (a.available && a.role !== "learned") {
      c.checked = true;
      picked.add(a.id);
    }
    c.addEventListener("change", () => {
      if (c.checked) picked.add(a.id);
      else picked.delete(a.id);
      update();
    });
    const role = a.role === "control" ? "control: same pipeline, no species prior" : a.role === "learned" ? "learned world" : "species profile";
    lab.append(c, " ", el("span", "mono", a.profile), ` on the ${a.world === "prior" ? "structured prior" : "learned world"} `, badge(role, a.role === "species" ? "teal" : "muted"));
    if (a.world === "learned" && !a.available) lab.append(badge("untrained", "warn"));
    if (!a.available) lab.append(el("span", "reason", a.reason));
    armBox.append(lab);
  }

  const secs = el("input");
  secs.type = "number";
  secs.min = "1";
  secs.max = "600";
  secs.value = "10";
  const secsLab = el("label", "seconds");
  secsLab.append("Seconds ", secs);
  const go = el("button", "btn primary", "Run");
  go.type = "button";
  const note = el("span", "note-inline muted");
  const actions = el("div", "actions");
  actions.append(secsLab, go, note);
  form.body.append(srcBox, armBox, actions);

  if (opts.prereg.length) {
    const pr = opts.prereg[0];
    const p = el("p", "prereg");
    p.append(badge("pre-registered", "teal"), ` ${pr.id ?? ""} frozen ${day(pr.frozen_at)} · hash ${pr.hash ?? "—"} · clips ${pr.clips.join(", ") || "—"} `, el("span", "src mono", pr.file));
    if (pr.verdict) p.append(" ", badge(`verdict: ${pr.verdict}`, "teal"), " ", el("span", "src mono", pr.verdict_file ?? ""));
    else p.append(" ", badge("no verdict yet", "muted"));
    form.body.append(p);
  } else {
    form.body.append(el("p", "muted small", "No frozen pre-registration for this species+sense: every run here is exploratory."));
  }

  const liveSlot = el("div");
  const resultSlot = el("div");
  body.append(form.box, liveSlot, resultSlot);

  const update = () => {
    const src = opts.sources.find((s) => s.id === source);
    const prereg = Boolean(src && opts.prereg.some((p) => p.clips.includes(src.name)));
    bannerSlot.replaceChildren(banners(null, opts, Boolean(src?.synthetic), prereg));
    const why = !source ? "no data source can run here" : !picked.size ? "pick at least one arm" : "";
    go.disabled = Boolean(why);
    note.textContent = why;
  };
  update();

  let live: Live | null = null;
  const follow = async (job: Job) => {
    live?.close();
    live = liveView(job.id, opts.view, Object.fromEntries(job.arms.map((a) => [a.bench_arm ?? a.id, a.id])));
    const b = banners(job, opts, job.synthetic, job.preregistered);
    liveSlot.replaceChildren(b, live.box);
    resultSlot.replaceChildren();
    await live.done;
    let j = job;
    for (let i = 0; i < 40; i++) {
      j = await api.job(job.id);
      if (j.status !== "running" && j.status !== "cancelling") break;
      await new Promise((r) => setTimeout(r, 250));
    }
    const res = panel("Side by side");
    res.head.append(badge(j.status, j.status === "succeeded" ? "teal" : j.status === "failed" ? "alert" : "muted"));
    if (j.error) res.body.append(el("p", "error", j.error));
    if (j.headline) res.body.append(el("p", "headline", j.headline));
    if (j.summaries.length) res.body.append(summaryTable(j));
    const rep = el("a", undefined, "replay report");
    rep.href = `/api/studio/jobs/${encodeURIComponent(j.id)}/report`;
    rep.target = "_blank";
    res.body.append(el("p", "small muted", `run ${j.id} · `), rep);
    resultSlot.replaceChildren(res.box);
    resultSlot.dataset.status = j.status;
  };

  go.addEventListener("click", async () => {
    if (!source) return;
    go.disabled = true;
    note.textContent = "starting…";
    try {
      const job = await api.run(clade, sense, { source, arms: [...picked], seconds: Number(secs.value) || 10 });
      note.textContent = "";
      await follow(job);
    } catch (e) {
      note.textContent = e instanceof Error ? e.message : String(e);
    } finally {
      update();
    }
  });

  const running = recent.find((j) => j.status === "running");
  if (running) void follow(running);

  if (recent.length) {
    const h = panel("Recent runs");
    const ul = el("ul", "recent");
    for (const j of recent) {
      const li = el("li");
      li.append(el("span", "mono", j.id), " ", badge(j.status, j.status === "succeeded" ? "teal" : j.status === "failed" ? "alert" : "muted"), ` ${j.source.name} · ${j.arms.map((a) => a.id).join(", ")}`);
      if (j.synthetic) li.append(" ", badge("synthetic", "warn"));
      if (!j.preregistered) li.append(" ", badge("not pre-registered", "muted"));
      ul.append(li);
    }
    h.body.append(ul);
    body.append(h.box);
  }
  body.append(inspect(opts));
}
