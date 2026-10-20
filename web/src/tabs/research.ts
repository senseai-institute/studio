// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Research: the research service's chat, focused on this species+sense, through Studio's proxy
// (/api/studio/research → RESEARCH_URL/api/research, research SPEC §8). Studio writes no prose
// here: every word comes from the research service, which has its own guardrails. Approvals
// happen on the service's pending-action cards.

import { badge, el, section } from "../dom.ts";

const BASE = "/api/studio/research";

interface Sse {
  event: string;
  data: string;
}

/** Split a Server-Sent Events buffer into complete events and the unfinished rest. */
export function parseSse(buf: string): { events: Sse[]; rest: string } {
  const blocks = buf.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events: Sse[] = [];
  for (const b of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of b.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length || event !== "message") events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

async function post(path: string, body: unknown): Promise<Response> {
  const r = await fetch(`${BASE}/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r;
}

export function researchTab(body: HTMLElement, clade: string, sense: string): void {
  const focus = `${clade}.senses.${sense}`;
  const sec = section("", "Research");
  sec.tools.append(badge(`focus: ${focus}`, "teal"), badge("answers come from the research service, not Studio", "muted"));
  const box = sec.box;
  box.classList.add("research");
  const log = el("div", "chat");
  log.setAttribute("aria-live", "polite");
  const form = el("form", "chat-form");
  const input = el("textarea");
  input.rows = 2;
  input.placeholder = `Ask about ${focus}…`;
  const send = el("button", "btn primary", "Send");
  send.type = "submit";
  form.append(input, send);
  sec.body.append(log, form);
  body.replaceChildren(box);

  let conv: string | null = null;
  const bubble = (who: "user" | "assistant", text = "") => {
    const b = el("div", `msg ${who}`, text);
    log.append(b);
    log.scrollTop = log.scrollHeight;
    return b;
  };

  const card = (payload: Record<string, unknown>) => {
    const c = el("div", "action-card");
    const id = String(payload.id ?? payload.action_id ?? "");
    c.append(el("div", "small muted", "Proposed change (needs your approval)"), el("div", undefined, String(payload.summary ?? payload.title ?? payload.label ?? id)));
    const why = el("textarea");
    why.rows = 2;
    why.placeholder = "Your rationale (required)";
    const ok = el("button", "btn primary", "Approve");
    const no = el("button", "btn", "Reject");
    const out = el("span", "small");
    for (const [btn, verb] of [[ok, "approve"], [no, "reject"]] as const) {
      btn.type = "button";
      btn.addEventListener("click", async () => {
        if (!why.value.trim()) {
          out.textContent = "a rationale is required";
          return;
        }
        try {
          await post(`actions/${encodeURIComponent(id)}/${verb}`, { rationale: why.value });
          out.textContent = verb === "approve" ? "approved" : "rejected";
          ok.disabled = no.disabled = true;
        } catch (e) {
          out.textContent = e instanceof Error ? e.message : String(e);
        }
      });
    }
    const row = el("div", "row");
    row.append(ok, no, out);
    c.append(why, row);
    log.append(c);
  };

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    bubble("user", text);
    const reply = bubble("assistant");
    send.disabled = true;
    try {
      if (!conv) conv = String(((await (await post("conversations", { focus: { library_path: focus } })).json()) as { id: string }).id);
      const r = await post(`conversations/${encodeURIComponent(conv)}/messages`, { text, focus: { library_path: focus } });
      const reader = r.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parsed = parseSse(buf);
        buf = parsed.rest;
        for (const e of parsed.events) {
          let d: Record<string, unknown> = {};
          try {
            d = JSON.parse(e.data) as Record<string, unknown>;
          } catch {
            d = { text: e.data };
          }
          if (e.event === "text_delta") reply.textContent += String(d.text ?? d.delta ?? "");
          else if (e.event === "tool_call") log.insertBefore(badge(String(d.label ?? d.name ?? "tool"), "muted"), reply);
          else if (e.event === "pending_action") card(d);
          else if (e.event === "job_progress") reply.dataset.progress = String(d.frac ?? "");
          else if (e.event === "error") log.append(el("p", "error", String(d.message ?? d.text ?? e.data)));
        }
        log.scrollTop = log.scrollHeight;
      }
    } catch (e) {
      log.append(el("p", "error", e instanceof Error ? e.message : String(e)));
    } finally {
      send.disabled = false;
    }
  });
}
