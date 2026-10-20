// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Research: the research service's assistant, focused on this species and sense, plus the
// context it works with. Everything here comes from the research service through Studio's proxy
// (../research/client.ts); Studio writes no prose of its own. Changes are proposals: nothing
// changes until a person approves a card with a reason.
//
//   chat (left)          context (right): To check · Claim · Impact · Experiment · Settings

import { badge, el, empty, errorBox, link } from "../dom.ts";
import { type ActionCard, arrow, type ChatEvent, chatEvent, focusPath, panelFor, startFor, transcriptEvents } from "../research/adapt.ts";
import { type ClaimCard, type ExperimentView, type Impact, research, type SettingsPage } from "../research/client.ts";

type Pane = "start" | "claim" | "impact" | "experiment" | "settings";
const PANES: [Pane, string][] = [
  ["start", "To check"],
  ["claim", "Claim"],
  ["impact", "Impact"],
  ["experiment", "Experiment"],
  ["settings", "Settings"],
];

export function researchTab(body: HTMLElement, clade: string, sense: string): void {
  const focus = focusPath(clade, sense);
  const grid = el("div", "research-grid");

  // ------------------------------------------------------------- chat
  const chat = el("section", "panel research-chat");
  const head = el("h2", undefined, "Research");
  head.append(badge(`focus: ${focus}`, "teal"), badge("answers come from the research service", "muted"));
  const log = el("div", "chat");
  log.setAttribute("aria-live", "polite");
  const form = el("form", "chat-form");
  const input = el("textarea");
  input.rows = 2;
  input.placeholder = `Ask about ${focus}…`;
  input.setAttribute("aria-label", "Your message");
  const send = el("button", "btn primary", "Send");
  send.type = "submit";
  form.append(input, send);
  chat.append(head, log, form);

  // ------------------------------------------------------------- context
  const ctx = el("section", "panel research-context");
  const tabs = el("div", "subtabs");
  tabs.setAttribute("role", "tablist");
  const panes = {} as Record<Pane, HTMLElement>;
  const buttons = {} as Record<Pane, HTMLButtonElement>;
  for (const [id, label] of PANES) {
    const b = el("button", "subtab", label);
    b.type = "button";
    b.id = `research-tab-${id}`;
    b.setAttribute("role", "tab");
    b.addEventListener("click", () => show(id));
    buttons[id] = b;
    tabs.append(b);
    const p = el("div", "pane");
    p.dataset.pane = id;
    p.setAttribute("role", "tabpanel");
    panes[id] = p;
  }
  panes.claim.append(empty("Pick a value under To check, or ask about one."));
  panes.impact.append(empty("When the assistant works out what a change does, it shows here."));
  panes.experiment.append(empty("Bench results show here, with the chance hit rate beside every hit rate."));
  ctx.append(tabs, ...Object.values(panes));
  grid.append(chat, ctx);
  body.replaceChildren(grid);

  function show(id: Pane): void {
    for (const [k, b] of Object.entries(buttons)) b.setAttribute("aria-selected", String(k === id));
    for (const [k, p] of Object.entries(panes)) p.hidden = k !== id;
    if (id === "settings") void load(panes.settings, research.settings(), settingsView);
  }

  async function load<T>(pane: HTMLElement, p: Promise<T>, view: (v: T) => HTMLElement): Promise<void> {
    pane.replaceChildren(el("p", "loading muted", "loading…"));
    try {
      pane.replaceChildren(view(await p));
    } catch (e) {
      pane.replaceChildren(errorBox(e));
    }
  }

  function open(panel: "claim" | "impact" | "experiment", id: string): void {
    show(panel);
    if (panel === "claim") void load(panes.claim, research.claim(id), claimView);
    else if (panel === "impact") void load(panes.impact, research.impact(id), impactView);
    else void load(panes.experiment, research.experiment(id), experimentView);
  }

  // ------------------------------------------------------------- start: what to check
  void load(panes.start, research.start(), (s) => {
    const { values, questions } = startFor(s, clade, sense);
    const box = el("div", "start");
    box.append(el("h3", undefined, "Least-verified values"));
    if (!values.length) box.append(empty(`No values from the ${clade} library in the research ledger yet.`));
    for (const v of values) {
      const row = el("button", "start-row");
      row.type = "button";
      row.dataset.claim = v.claim_id;
      const st = badge(v.status, v.status === "verified" ? "teal" : "warn");
      st.dataset.status = v.status;
      row.append(st, el("span", "mono", v.library_path), el("span", "value", v.value));
      row.title = v.why;
      row.addEventListener("click", () => {
        claimFocus = v.claim_id;
        open("claim", v.claim_id);
      });
      box.append(row);
    }
    box.append(el("h3", undefined, "Open questions"));
    if (!questions.length) box.append(empty(`No open questions for ${clade}.`));
    for (const q of questions) {
      const row = el("div", "question");
      row.append(badge(q.priority || "open", q.priority === "high" ? "warn" : "muted"), el("span", undefined, q.statement));
      box.append(row);
    }
    return box;
  });
  show("start");

  // ------------------------------------------------------------- the conversation
  const key = `research:conversation:${focus}`;
  let conv: string | null = null;
  let claimFocus: string | null = null;
  try {
    conv = sessionStorage.getItem(key);
  } catch {
    conv = null;
  }
  let reply: HTMLElement | null = null;
  const chips = new Map<string, HTMLElement>();

  function render(e: ChatEvent | { kind: "user" | "note"; text: string }): void {
    switch (e.kind) {
      case "user":
        reply = null;
        log.append(el("div", "msg user", e.text));
        break;
      case "note":
        log.append(el("div", "msg note", e.text));
        break;
      case "text":
        if (!reply) {
          reply = el("div", "msg assistant");
          log.append(reply);
        }
        reply.textContent += e.text;
        break;
      case "thinking": {
        const d = el("details", "thinking");
        d.append(el("summary", undefined, "How the assistant is thinking"), el("p", "muted", e.text));
        log.append(d);
        reply = null;
        break;
      }
      case "tool": {
        const c = badge(e.label, "muted");
        c.classList.add("tool-chip");
        c.dataset.state = "running";
        chips.set(e.id, c);
        log.append(c);
        reply = null;
        break;
      }
      case "tool_done": {
        const c = chips.get(e.id);
        if (c) {
          c.dataset.state = e.ok ? "ok" : "problem";
          c.title = e.summary;
        }
        const target = panelFor(e.refs);
        if (target) open(target.panel, target.id);
        break;
      }
      case "card":
        log.append(cardView(e.card));
        reply = null;
        break;
      case "progress": {
        const m = el("div", "msg job", `${e.message}${e.frac === null ? "" : ` (${Math.round(e.frac * 100)}%)`}`);
        log.append(m);
        break;
      }
      case "error":
        log.append(el("p", "error", e.message));
        break;
      case "done":
      case "ignored":
        break;
    }
    log.scrollTop = log.scrollHeight;
  }

  function cardView(c: ActionCard): HTMLElement {
    const box = el("div", "action-card");
    box.dataset.status = c.status;
    box.dataset.action = c.id;
    box.append(el("div", "small muted", "Proposed change (needs your approval)"), el("strong", undefined, c.title));
    if (c.summary) box.append(el("p", undefined, c.summary));
    if (c.rows.length) {
      const t = el("table", "grid");
      for (const r of c.rows) {
        const tr = el("tr");
        tr.append(el("th", undefined, r.label), el("td", undefined, r.before), el("td", "muted", "→"), el("td", "after", r.after));
        t.append(tr);
      }
      box.append(t);
    }
    if (c.quote) box.append(el("blockquote", "passage", `“${c.quote}”`));
    if (c.note) box.append(el("p", "small muted", c.note));
    const out = el("p", "small card-status", c.status === "pending" ? "Nothing changes until you approve." : c.status);
    if (c.status !== "pending") {
      box.append(out);
      return box;
    }
    const why = el("textarea", "rationale");
    why.rows = 2;
    why.placeholder = "Your reason, in one sentence (required)";
    const ok = el("button", "btn primary", "Approve");
    const no = el("button", "btn", "Reject");
    for (const [btn, verb] of [[ok, "approve"], [no, "reject"]] as const) {
      btn.type = "button";
      btn.addEventListener("click", async () => {
        if (why.value.trim().split(/\s+/).length < 3) {
          out.textContent = "Write your reason as a full sentence first.";
          return;
        }
        ok.disabled = no.disabled = true;
        try {
          const r = await research.decide(c.id, verb, why.value.trim());
          box.dataset.status = r.action.status;
          out.textContent = r.message;
          why.remove();
          ok.remove();
          no.remove();
          if (claimFocus) open("claim", claimFocus);
        } catch (e) {
          out.textContent = e instanceof Error ? e.message : String(e);
          ok.disabled = no.disabled = false;
        }
      });
    }
    const actions = el("div", "card-actions");
    actions.append(ok, no);
    box.append(why, actions, out);
    return box;
  }

  if (conv) {
    research
      .conversation(conv)
      .then((c) => transcriptEvents(c.items).forEach(render))
      .catch(() => {
        conv = null;
      });
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    render({ kind: "user", text });
    send.disabled = true;
    try {
      if (!conv) {
        conv = (await research.newConversation()).id;
        try {
          sessionStorage.setItem(key, conv);
        } catch {
          /* private mode: the conversation lasts until the page closes */
        }
      }
      const focusArg: Record<string, string> = claimFocus ? { claim_id: claimFocus } : { library_path: focus };
      for await (const e of research.send(conv, text, focusArg)) render(chatEvent(e.event, e.data));
    } catch (e) {
      log.append(el("p", "error", e instanceof Error ? e.message : String(e)));
    } finally {
      send.disabled = false;
    }
  });
}

// ------------------------------------------------------------- context views

function claimView(c: ClaimCard): HTMLElement {
  const box = el("div", "claim-view");
  const h = el("div", "claim-head");
  const st = badge(c.claim.status, c.claim.status === "verified" ? "teal" : "warn");
  st.dataset.status = c.claim.status;
  h.append(el("span", "mono", c.claim.library_path), st);
  box.append(h, el("div", "claim-value", c.value));
  const facts = el("dl", "kv");
  for (const [k, v] of [
    ["Species", c.claim.species],
    ["Conditions", c.claim.conditions],
    ["Method", c.claim.method],
    ["Matches the library field", c.claim.mapping],
    ["Why unverified", c.claim.unverified_reason],
  ] as const) {
    if (!v) continue;
    facts.append(el("dt", undefined, k), el("dd", undefined, v));
  }
  box.append(facts);
  if (c.passage) {
    const q = el("blockquote", "passage");
    q.append(el("span", "ctx", c.passage.before), el("mark", undefined, c.passage.quote), el("span", "ctx", c.passage.after));
    box.append(el("h3", undefined, c.passage.section || "Passage"), q);
  }
  for (const s of c.sources) {
    const p = el("p", "small");
    p.append(`${s.authors} (${s.year ?? "n.d."}) ${s.title} `);
    if (s.link) p.append(link(s.doi ?? "link", s.link, true));
    p.append(" ", badge(s.full_text ? "full text" : "abstract only", s.full_text ? "teal" : "warn"));
    box.append(p);
  }
  box.append(el("h3", undefined, "History"));
  const ol = el("ol", "history");
  for (const r of c.history) {
    const li = el("li");
    li.append(el("strong", undefined, `Revision ${r.revision}`), ` ${r.summary} — ${r.by}, ${r.at.slice(0, 10)}`);
    if (r.reason) li.append(el("div", "small muted", r.reason));
    ol.append(li);
  }
  if (!c.history.length) ol.append(el("li", "muted", "As imported from the library; never changed."));
  box.append(ol);
  return box;
}

function impactView(i: Impact): HTMLElement {
  const box = el("div", "impact-view");
  box.append(el("h3", undefined, `What changing ${i.library_path} does`));
  const ul = el("ul");
  for (const s of [...i.field_summaries.map((f) => f.sentence), ...i.sentences]) ul.append(el("li", undefined, s));
  box.append(ul);
  box.append(el("h3", undefined, "Robot settings that read it"));
  const cons = el("ul", "mono small");
  for (const c of i.consumers) cons.append(el("li", undefined, c));
  box.append(cons);
  if (i.reflex_rows.length) {
    const t = el("table", "grid");
    t.append(el("tr"));
    t.rows[0].append(el("th", undefined, "Arm"), el("th", undefined, "Reflex θ"));
    for (const r of i.reflex_rows) {
      const tr = el("tr");
      tr.append(el("td", undefined, r.arm), el("td", undefined, arrow(r.theta_old, r.theta_new, (v) => (v === null ? "—" : v.toFixed(3)))));
      t.append(tr);
    }
    box.append(t);
  }
  const w = el("p", `note ${i.world_reached ? "" : "warn"}`.trim(), i.world_note);
  w.dataset.worldReached = String(i.world_reached);
  box.append(w);
  return box;
}

function experimentView(x: ExperimentView): HTMLElement {
  const box = el("div", "experiment-view");
  const st = badge(x.experiment.status, x.experiment.status === "done" ? "teal" : x.experiment.status === "failed" ? "alert" : "muted");
  box.append(el("p", "small mono", `${x.experiment.sequences.join(", ")} · bench ${x.experiment.bench_sha}`), st);
  if (x.experiment.error) box.append(el("p", "error", x.experiment.error));
  if (x.progress?.message) box.append(el("p", "muted", x.progress.message));
  if (x.comparison.length) {
    const t = el("table", "grid experiment-table");
    const hr = el("tr");
    for (const h of ["Arm", "Objects", "Hit rate (before → after)", "Chance hit rate", "Median delay (s)", "False fires / h"]) hr.append(el("th", undefined, h));
    t.append(hr);
    const n = (v: number | null) => (v === null ? "—" : String(Number(v.toPrecision(3))));
    for (const c of x.comparison) {
      const tr = el("tr");
      tr.append(el("td", undefined, c.arm), el("td", undefined, c.objects === null ? "—" : String(c.objects)));
      if (!c.judged) {
        const td = el("td", "too-few", c.verdict || "too few objects to judge");
        td.colSpan = 4;
        tr.append(td);
      } else {
        tr.append(
          el("td", undefined, arrow(c.baseline_hit_rate, c.patched_hit_rate)),
          el("td", "muted", arrow(c.baseline_chance_hit_rate, c.patched_chance_hit_rate)),
          el("td", undefined, arrow(c.baseline_median_delay_s, c.patched_median_delay_s, n)),
          el("td", undefined, arrow(c.baseline_fires_per_h, c.patched_fires_per_h, n)),
        );
      }
      t.append(tr);
    }
    box.append(t);
  }
  return box;
}

const NEED: Record<string, string> = { required: "Required", recommended: "Recommended", optional: "Optional", none: "No key needed" };

function settingsView(s: SettingsPage): HTMLElement {
  const box = el("div", "settings-view");
  box.append(el("p", "muted", s.where));
  for (const g of s.groups) {
    box.append(el("h3", undefined, g));
    const t = el("table", "grid settings-table");
    for (const i of s.integrations.filter((x) => x.group === g)) {
      const tr = el("tr");
      tr.dataset.service = i.id;
      tr.dataset.state = i.state;
      const name = el("td");
      const more = el("details");
      more.append(el("summary", undefined, i.name), el("p", "small", i.purpose), el("p", "small muted", `Without it: ${i.without}`), el("p", "small muted", `Get a key: ${i.get_key}`));
      name.append(more);
      const state =
        i.state === "no_key" ? "No key needed" : i.state === "set" ? "Set" : i.state === "partial" ? `Partly set; missing ${i.vars.filter((v) => !v.set).map((v) => v.name).join(", ")}` : "Not set";
      const keyCell = el("td");
      keyCell.append(badge(state, i.state === "set" ? "teal" : i.state === "no_key" ? "muted" : "warn"));
      for (const v of i.vars) keyCell.append(el("div", "mono small", v.name));
      const test = el("td");
      if (i.checkable) {
        const b = el("button", "btn small", "Test");
        b.type = "button";
        const out = el("span", "check-result small");
        b.addEventListener("click", async () => {
          b.disabled = true;
          out.textContent = "testing…";
          try {
            const r = await research.checkKey(i.id);
            out.textContent = r.detail;
            out.dataset.ok = String(r.ok);
          } catch (e) {
            out.textContent = e instanceof Error ? e.message : String(e);
            out.dataset.ok = "false";
          } finally {
            b.disabled = false;
          }
        });
        test.append(b, out);
      }
      tr.append(name, el("td", undefined, NEED[i.need] ?? i.need), keyCell, test);
      t.append(tr);
    }
    box.append(t);
  }
  return box;
}
