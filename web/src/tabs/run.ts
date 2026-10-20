// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Run: §1 Protocol (data, arms, duration), §2 Observation (live), §3 Result (side by side and
// the replay report). Every option the server cannot run stays visible with its reason;
// banners say what a run is not.

import { api, type Job, type RunOptions } from "../api.ts";
import { badge, el, empty, inspect, link, section, srcRef, table, tags, td } from "../dom.ts";
import { day, ms, pct } from "../format.ts";
import { liveView, type Live } from "../live.ts";

function banners(job: Job | null, opts: RunOptions, synthetic: boolean, preregistered: boolean): HTMLElement {
  const b = el("div", "banners");
  if (synthetic) b.append(el("p", "banner warn", "Synthetic data: shows the pipeline, not a result."));
  if (!preregistered) b.append(el("p", "banner", "Not pre-registered: an exploratory run, not evidence for a claim."));
  if (job?.arms.some((a) => a.world === "prior")) b.append(el("p", "banner", "World: structured prior (no training)."));
  if (opts.arms.every((a) => a.role !== "species")) b.append(el("p", "banner", "No profile reads this sense yet: only the control runs."));
  return b;
}

function resultTable(job: Job): HTMLElement {
  const { wrap, tb } = table(["arm", "sequence", ["caught", "num"], ["median delay", "num"], ["false fires / h", "num"], ["latency p50", "num"], ["latency p99", "num"]]);
  for (const s of job.summaries) {
    const tr = el("tr");
    tr.append(td(el("span", "mono", job.arms.find((a) => a.bench_arm === s.arm)?.id ?? String(s.arm ?? ""))), td(el("span", "mono", String(s.sequence ?? ""))));
    if (s.error) {
      const c = el("td", "error", String(s.error));
      c.colSpan = 5;
      tr.append(c);
    } else {
      tr.append(
        td(s.hit_rate === null || s.hit_rate === undefined ? "— (no labels)" : pct(s.hit_rate), "num"),
        td(typeof s.median_delay_s === "number" ? `${s.median_delay_s.toFixed(2)} s` : "—", "num"),
        td(typeof s.unattributed_fires_per_h === "number" ? s.unattributed_fires_per_h.toFixed(1) : "—", "num"),
        td(ms(s.latency_p50_ms), "num"),
        td(ms(s.latency_p99_ms), "num"),
      );
    }
    tb.append(tr);
  }
  return wrap;
}

export async function runTab(body: HTMLElement, clade: string, sense: string): Promise<void> {
  const [opts, recent] = await Promise.all([api.runOptions(clade, sense), api.jobs(clade, sense).catch(() => [] as Job[])]);
  body.replaceChildren();

  // §1 protocol
  const s1 = section("§1", "Protocol");
  s1.tools.append(opts.bench.found ? badge("senseai-bench", "teal", Object.entries(opts.bench.features).map(([k, v]) => `${k}: ${v ? "yes" : "no"}`).join("\n")) : badge("senseai-bench not found", "alert", opts.bench.error ?? ""));
  const bannerSlot = el("div");
  const grid = el("div", "grid-2");

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
    const what = el("span", "what");
    if (s.synthetic) what.append(el("span", undefined, "Synthetic stream"), el("span", "faint mono small", (s.streams ?? []).join(" + ").toLowerCase()), badge("synthetic", "warn"));
    else what.append(el("span", "mono", s.name), el("span", "faint small", s.dataset), badge(s.labelled ? "labelled" : "no labels", s.labelled ? "teal" : "muted"));
    lab.append(r, what);
    if (!s.available) lab.append(el("span", "reason", s.reason));
    srcBox.append(lab);
  }
  if (opts.sources.length && opts.sources.every((s) => s.synthetic)) srcBox.append(el("p", "faint small", "No recordings for this modality under SENSEAI_DATA_ROOT yet: synthetic only."));

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
    const role = a.role === "control" ? "control" : a.role === "learned" ? "learned world" : "species";
    const what = el("span", "what");
    what.append(el("span", "mono", a.profile), el("span", "faint small", a.world === "prior" ? "structured prior" : `${a.world} world`), badge(role, a.role === "species" ? "teal" : "muted", a.role === "control" ? "same pipeline, no species prior" : ""));
    if (a.world === "learned" && !a.available) what.append(badge("untrained", "warn"));
    lab.append(c, what);
    if (!a.available) lab.append(el("span", "reason", a.reason));
    else if (a.description) lab.append(el("span", "reason", a.description));
    armBox.append(lab);
  }
  grid.append(srcBox, armBox);

  const bar = el("div", "run-bar");
  const secs = el("input");
  secs.type = "number";
  secs.min = "1";
  secs.max = "600";
  secs.value = "10";
  const secsLab = el("label");
  secsLab.append("Duration", secs, "s");
  const go = el("button", "btn primary", "Run");
  go.type = "button";
  const note = el("span", "faint small");
  bar.append(secsLab, go, note);

  const pre = el("div");
  if (opts.prereg.length) {
    const pr = opts.prereg[0];
    const p = el("p", "note");
    p.append(tags(badge("pre-registered", "teal"), pr.verdict ? badge(`verdict: ${pr.verdict}`, "teal") : badge("no verdict yet", "muted")), ` ${pr.id ?? ""} · frozen ${day(pr.frozen_at)} · hash ${pr.hash ?? "—"} · clips ${pr.clips.join(", ") || "—"} `, srcRef(pr.file));
    if (pr.verdict_file) p.append(" ", srcRef(pr.verdict_file));
    pre.append(p);
  } else pre.append(el("p", "faint small", "No frozen pre-registration for this species and sense: every run here is exploratory."));
  s1.body.append(bannerSlot, grid, bar, pre);
  body.append(s1.box);

  // §2 observation, §3 result
  const s2 = section("§2", "Observation");
  const liveSlot = el("div");
  liveSlot.append(empty("Press Run to stream the pipeline live: the frame with the bearing ring, surprise per arm, the reflex state and its fires."));
  s2.body.append(liveSlot);
  const s3 = section("§3", "Result");
  const resultSlot = el("div");
  resultSlot.append(empty("The side-by-side appears here when a run ends."));
  s3.body.append(resultSlot);
  body.append(s2.box, s3.box);

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
    liveSlot.replaceChildren(banners(job, opts, job.synthetic, job.preregistered), live.box);
    resultSlot.replaceChildren(el("p", "empty", "running…"));
    s2.box.scrollIntoView({ behavior: "smooth", block: "start" });
    await live.done;
    let j = job;
    for (let i = 0; i < 40; i++) {
      j = await api.job(job.id);
      if (j.status !== "running" && j.status !== "cancelling") break;
      await new Promise((r) => setTimeout(r, 250));
    }
    const out = el("div");
    out.style.display = "grid";
    out.style.gap = "10px";
    out.append(tags(badge(j.status, j.status === "succeeded" ? "teal" : j.status === "failed" ? "alert" : "muted"), j.synthetic ? badge("synthetic", "warn") : null, j.preregistered ? badge("pre-registered clip", "teal") : badge("not pre-registered", "muted")));
    if (j.error) out.append(el("p", "note alert", j.error));
    if (j.headline) out.append(el("p", "headline", j.headline));
    if (j.summaries.length) out.append(resultTable(j));
    const foot = el("p", "faint small");
    foot.append(`run ${j.id} · `, link("replay report", `/api/studio/jobs/${encodeURIComponent(j.id)}/report`, true));
    out.append(foot);
    resultSlot.replaceChildren(out);
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
    const h = section("", "Previous runs");
    const { wrap, tb } = table(["run", "status", "data", "arms", "caveats"]);
    for (const j of recent) {
      const tr = el("tr");
      tr.append(
        td(el("span", "mono small", j.id)),
        td(badge(j.status, j.status === "succeeded" ? "teal" : j.status === "failed" ? "alert" : "muted")),
        td(j.source.name),
        td(el("span", "mono small", j.arms.map((a) => a.id).join(", "))),
        td(tags(j.synthetic ? badge("synthetic", "warn") : null, j.preregistered ? null : badge("not pre-registered", "muted"))),
      );
      tb.append(tr);
    }
    h.body.append(wrap);
    body.append(h.box);
  }
  body.append(inspect(opts));
}
