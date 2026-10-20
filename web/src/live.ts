// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// The live view of a run: the latest frame (camera/event frame, or a spectrogram image when the
// producer sends one) with the bearing ring (as in the viewer) over it, the global surprise trace per
// arm, a reflex state pill, latency p99 and the fires as they happen. Fed by the live events
// contract (bench --events): run_start, arm_start, progress, sample, fire, gt, arm_end, run_end,
// plus the optional `frame` events and `sample.ring`; unknown types and fields are ignored.

import { api } from "./api.ts";
import { badge, el } from "./dom.ts";
import { ms, pct } from "./format.ts";

type Ev = Record<string, unknown> & { type: string };

const COLORS = ["#5eead4", "#a9b4ca", "#f2b35c", "#ff5a7a", "#8ab4ff"];

/** Bearing ring: bin b is centred on b·360/B degrees, 0 = straight ahead (up), CCW positive. */
export function drawRing(ctx: CanvasRenderingContext2D, W: number, H: number, ring: number[] | null, fires: number[]): void {
  const cx = W / 2;
  const cy = H / 2;
  const r = Math.min(W, H) * 0.42;
  ctx.save();
  ctx.strokeStyle = "rgba(154,164,184,.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
  if (ring && ring.length) {
    const B = ring.length;
    const max = Math.max(1e-6, ...ring);
    for (let b = 0; b < B; b++) {
      const v = ring[b] / max;
      if (v <= 0.05) continue;
      const a0 = -Math.PI / 2 - ((b - 0.5) * 2 * Math.PI) / B;
      const a1 = -Math.PI / 2 - ((b + 0.5) * 2 * Math.PI) / B;
      ctx.strokeStyle = `rgba(94,234,212,${0.25 + 0.75 * v})`;
      ctx.lineWidth = 3 + 9 * v;
      ctx.beginPath();
      ctx.arc(cx, cy, r, a1, a0);
      ctx.stroke();
    }
  }
  for (const deg of fires) {
    const a = -Math.PI / 2 - (deg * Math.PI) / 180;
    ctx.fillStyle = "#ff5a7a";
    ctx.beginPath();
    ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 6, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawTrace(ctx: CanvasRenderingContext2D, W: number, H: number, series: Map<string, [number, number][]>, duration: number): void {
  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(154,164,184,.25)";
  ctx.beginPath();
  ctx.moveTo(0, H - 0.5);
  ctx.lineTo(W, H - 0.5);
  ctx.stroke();
  let max = 1e-6;
  for (const pts of series.values()) for (const [, v] of pts) max = Math.max(max, v);
  let i = 0;
  for (const pts of series.values()) {
    ctx.strokeStyle = COLORS[i++ % COLORS.length];
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach(([t, v], k) => {
      const x = (t / Math.max(duration, 1e-6)) * W;
      const y = H - 4 - (v / max) * (H - 8);
      if (k) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
    });
    ctx.stroke();
  }
}

export interface Live {
  box: HTMLElement;
  done: Promise<void>;
  close(): void;
}

export function liveView(jobId: string, view: string | null, labels: Record<string, string> = {}): Live {
  const box = el("section", "live panel");
  box.dataset.job = jobId;
  const head = el("h2", undefined, "Live");
  const status = el("span", "live-status muted", "connecting…");
  head.append(status);
  const grid = el("div", "live-grid");
  const stage = el("div", "live-stage");
  const img = el("img", "frame");
  img.alt = "latest frame from the run";
  const ring = el("canvas", "ring");
  ring.width = 480;
  ring.height = 360;
  ring.setAttribute("role", "img");
  ring.setAttribute("aria-label", "bearing ring: where the model's surprise points, red dots are reflex fires");
  const noFrame = el("div", "no-frame muted", view === "spectrogram" ? "waiting for a spectrogram from the run…" : view === "trace" ? "this sense streams a trace, not images" : "waiting for frames from the run…");
  stage.append(img, ring, noFrame);
  const side = el("div", "live-side");
  const arms = el("div", "arm-cards");
  const trace = el("canvas", "trace");
  trace.width = 600;
  trace.height = 120;
  trace.setAttribute("aria-label", "global surprise over time, one line per arm");
  const legend = el("div", "legend");
  const feed = el("ul", "feed");
  side.append(arms, el("div", "k muted small", "global surprise"), trace, legend, el("div", "k muted small", "events"), feed);
  grid.append(stage, side);
  box.append(head, grid);

  const series = new Map<string, [number, number][]>();
  const cards = new Map<string, { state: HTMLElement; p99: HTMLElement; pill: HTMLElement; bar: HTMLElement }>();
  let duration = 1;
  let lastRing: number[] | null = null;
  let ringArm: string | null = null;
  const fires: number[] = [];
  const ctx = ring.getContext("2d")!;
  const tctx = trace.getContext("2d")!;
  const card = (arm: string) => {
    let c = cards.get(arm);
    if (c) return c;
    const i = cards.size;
    const d = el("div", "arm-card");
    d.dataset.arm = arm;
    const sw = el("i");
    sw.style.background = COLORS[i % COLORS.length];
    const name = el("div", "arm-name");
    name.append(sw, labels[arm] ?? arm);
    const pill = el("span", "pill idle", "idle");
    const p99 = el("span", "mono small", "p99 —");
    const state = el("div", "muted small", "waiting");
    const bar = el("div", "bar");
    bar.append(el("i"));
    d.append(name, pill, p99, bar, state);
    arms.append(d);
    const li = el("span");
    const sw2 = el("i");
    sw2.style.background = COLORS[i % COLORS.length];
    li.append(sw2, labels[arm] ?? arm);
    legend.append(li);
    c = { state, p99, pill, bar };
    cards.set(arm, c);
    return c;
  };
  const redraw = () => {
    ctx.clearRect(0, 0, ring.width, ring.height);
    drawRing(ctx, ring.width, ring.height, lastRing, fires);
    drawTrace(tctx, trace.width, trace.height, series, duration);
  };

  let resolve!: () => void;
  const done = new Promise<void>((r) => (resolve = r));
  const es = new EventSource(api.eventsUrl(jobId));
  es.onmessage = (m) => {
    let ev: Ev;
    try {
      ev = JSON.parse(m.data) as Ev;
    } catch {
      return;
    }
    const arm = typeof ev.arm === "string" ? ev.arm : null;
    switch (ev.type) {
      case "run_start": {
        status.textContent = "running";
        for (const a of (ev.arms as { name: string }[]) ?? []) card(a.name);
        const seqs = (ev.sequences as { duration_s?: number }[]) ?? [];
        duration = Math.max(1, ...seqs.map((s) => s.duration_s ?? 1));
        break;
      }
      case "arm_start":
        if (arm) card(arm).state.textContent = `running on ${String(ev.sequence ?? "")}`;
        break;
      case "frame":
        if (typeof ev.path === "string") {
          img.src = api.fileUrl(jobId, ev.path);
          noFrame.hidden = false;
          noFrame.textContent = ev.kind === "rgb" ? "camera frame" : ev.kind === "surprise_grid" ? "world surprise grid (this run has no camera frame)" : String(ev.kind ?? "frame");
          box.dataset.frames = String(Number(box.dataset.frames ?? 0) + 1);
        }
        break;
      case "sample": {
        if (!arm) break;
        const v = typeof ev.value === "number" ? ev.value : null;
        if (v !== null) {
          const pts = series.get(arm) ?? [];
          pts.push([Number(ev.t_rel_s ?? 0), v]);
          series.set(arm, pts);
        }
        const c = card(arm);
        c.pill.textContent = ev.active ? "acting" : "idle";
        c.pill.className = `pill ${ev.active ? "acting" : "idle"}`;
        if (Array.isArray(ev.ring) && (ringArm === null || ringArm === arm)) {
          ringArm = arm;
          lastRing = ev.ring as number[];
        }
        redraw();
        break;
      }
      case "progress":
        if (arm) {
          const c = card(arm);
          c.p99.textContent = `p99 ${ms(ev.latency_p99_ms)}`;
          (c.bar.firstElementChild as HTMLElement).style.width = pct(ev.frac);
        }
        break;
      case "fire": {
        const li = el("li");
        li.append(el("span", "t", `${Number(ev.t_rel_s ?? 0).toFixed(2)} s`), el("span"));
        li.lastElementChild!.append(el("span", "kind fire", "fire"), `${arm ? (labels[arm] ?? arm) : ""}${typeof ev.bearing_deg === "number" ? ` · ${ev.bearing_deg.toFixed(0)}°` : ""}${ev.explain ? ` · ${String(ev.explain)}` : ""}`);
        feed.prepend(li);
        if (typeof ev.bearing_deg === "number" && (ringArm === null || ringArm === arm)) fires.push(ev.bearing_deg);
        redraw();
        break;
      }
      case "gt": {
        const li = el("li");
        li.append(el("span", "t", `${Number(ev.t_rel_s ?? 0).toFixed(2)} s`), el("span", undefined, `ground truth: ${String(ev.cls ?? "")}`));
        feed.prepend(li);
        break;
      }
      case "arm_end":
        if (arm) card(arm).state.textContent = ev.error ? `error: ${String(ev.error)}` : "done";
        break;
      case "run_end":
        status.replaceChildren(ev.error ? badge(`failed: ${String(ev.error)}`, "alert") : badge("finished", "teal"));
        es.close();
        resolve();
        break;
      default:
        break;
    }
  };
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) {
      status.textContent = "stream closed";
      resolve();
    }
  };
  redraw();
  return { box, done, close: () => es.close() };
}
