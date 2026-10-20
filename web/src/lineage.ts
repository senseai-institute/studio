// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Fig. 1 of the Model tab: from cited values to model parameters. Left, the library values
// (with their values from the Sources response); middle, the rule that reads each one (or the
// world prior's from_library); right, the model parameter it sets, with the computed value.
// Drawn from data only; nothing here is laid out by hand.

import type { Model, Sources } from "./api.ts";
import { value } from "./format.ts";

const NS = "http://www.w3.org/2000/svg";
const W = [300, 210, 300];
const X = [0, 360, 630];
const H = 40;
const GAP = 10;

interface Node {
  id: string;
  col: 0 | 1 | 2;
  title: string;
  sub: string;
  cls: string;
}

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}): SVGElementTagNameMap[K] {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

function clip(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Nodes and edges, or null when nothing in the model reads this sense. */
export function lineageData(model: Model, sources: Sources): { nodes: Node[]; edges: [string, string, string][] } | null {
  const vals = new Map(sources.quantities.map((q) => [q.path, q]));
  const nodes = new Map<string, Node>();
  const edges: [string, string, string][] = [];
  const add = (n: Node) => {
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  };
  const libNode = (path: string) => {
    const q = vals.get(path);
    add({
      id: `L:${path}`,
      col: 0,
      title: q ? `${q.description ?? path.split(".").slice(3).join(" ")}` : path.split(".").slice(2).join("."),
      sub: q ? `${value(q.value)} ${q.unit} · ${q.species ?? ""}` : path,
      cls: "lib",
    });
  };
  for (const p of model.profiles) {
    for (const f of p.fields) {
      if (f.kind !== "rule" || !f.reads_this_sense) continue;
      for (const path of Object.values(f.library_paths ?? {})) {
        libNode(path);
        const rid = `R:${f.rule}`;
        add({ id: rid, col: 1, title: f.rule ?? "rule", sub: f.output ?? "", cls: "rule" });
        const fid = `F:${p.name}.${f.section}.${f.field}`;
        const v = typeof f.value === "number" ? value(Math.round(f.value * 1000) / 1000) : f.output === "gain_lut" || f.output === "attention" ? "curve" : "—";
        add({ id: fid, col: 2, title: `${p.name}.${f.section}.${f.field}`, sub: `= ${v}`, cls: "field" });
        edges.push([`L:${path}`, rid, ""], [rid, fid, ""]);
      }
    }
  }
  const prefix = `${model.clade}.senses.${model.sense}`.toLowerCase();
  for (const w of model.world_prior.params) {
    if (!w.reads_this_sense) continue;
    const m = w.source.match(/^([A-Za-z]+\.senses\.[a-z0-9_]+\.[a-z0-9_.]+)/);
    const path = m ? m[1].toLowerCase() : prefix;
    libNode(path);
    add({ id: "R:from_library", col: 1, title: "PriorParams.from_library", sub: "world prior", cls: "rule" });
    const wid = `W:${w.name}`;
    add({ id: wid, col: 2, title: `world.${w.name}`, sub: `= ${value(w.value)} · ${w.kind}`, cls: "world" });
    edges.push([`L:${path}`, "R:from_library", "world"], ["R:from_library", wid, "world"]);
  }
  if (!nodes.size) return null;
  const seen = new Set<string>();
  return { nodes: [...nodes.values()], edges: edges.filter((e) => (seen.has(e.join()) ? false : (seen.add(e.join()), true))) };
}

export function lineageSvg(data: NonNullable<ReturnType<typeof lineageData>>): SVGSVGElement {
  const cols: Node[][] = [[], [], []];
  for (const n of data.nodes) cols[n.col].push(n);
  const rows = Math.max(...cols.map((c) => c.length));
  const height = 28 + rows * (H + GAP);
  const pos = new Map<string, { x: number; y: number; w: number }>();
  cols.forEach((c, ci) => {
    const off = ((rows - c.length) * (H + GAP)) / 2;
    c.forEach((n, i) => pos.set(n.id, { x: X[ci], y: 28 + off + i * (H + GAP), w: W[ci] }));
  });
  const width = X[2] + W[2] + 2;
  const s = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Lineage: cited values, rules, model parameters" });
  ["Cited value (library)", "Rule", "Model parameter"].forEach((t, i) => {
    const tx = svg("text", { x: X[i], y: 12, class: "col-title" });
    tx.textContent = t;
    s.append(tx);
  });
  for (const [a, b, cls] of data.edges) {
    const p = pos.get(a)!;
    const q = pos.get(b)!;
    const x1 = p.x + p.w;
    const y1 = p.y + H / 2;
    const x2 = q.x;
    const y2 = q.y + H / 2;
    const mx = (x1 + x2) / 2;
    s.append(svg("path", { d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, class: `edge ${cls}` }));
  }
  for (const n of data.nodes) {
    const p = pos.get(n.id)!;
    const g = svg("g", { class: `node ${n.cls}`, transform: `translate(${p.x},${p.y})` });
    g.append(svg("rect", { width: p.w, height: H, rx: 5 }));
    const t1 = svg("text", { x: 9, y: 16 });
    t1.textContent = clip(n.title, Math.floor(p.w / 6.6));
    const t2 = svg("text", { x: 9, y: 31, class: "sub" });
    t2.textContent = clip(n.sub, Math.floor(p.w / 6.4));
    const tip = svg("title");
    tip.textContent = `${n.title}\n${n.sub}`;
    g.append(tip, t1, t2);
    s.append(g);
  }
  return s;
}
