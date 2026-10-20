// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// The adapters against payloads recorded from the research service itself
// (fixtures/research_events.json), so a change in research's shapes fails here.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { actionCard, arrow, chatEvent, panelFor, pct, startFor, transcriptEvents } from "./adapt.ts";
import { parseSse } from "./client.ts";

const rec = JSON.parse(readFileSync(new URL("./fixtures/research_events.json", import.meta.url), "utf8")) as {
  events: { event: string; data: unknown }[];
  transcript: { kind: string }[];
};
const live = rec.events.map((e) => chatEvent(e.event, JSON.stringify(e.data)));

test("every recorded event maps to something Studio renders", () => {
  assert.deepEqual(live.filter((e) => e.kind === "ignored"), []);
  const kinds = new Set(live.map((e) => e.kind));
  for (const k of ["text", "thinking", "tool", "tool_done", "card", "done"]) assert.ok(kinds.has(k as never), k);
});

test("the pending action card has the id to approve and the change to show", () => {
  const card = live.find((e) => e.kind === "card");
  assert.ok(card && card.kind === "card");
  assert.match(card.card.id, /^act-/);
  assert.equal(card.card.kind, "claim_revision");
  assert.equal(card.card.status, "pending");
  assert.ok(card.card.title.length > 0);
  assert.ok(card.card.rows.some((r) => r.before.includes("-0.74") && r.after.includes("-0.08")));
  assert.ok(card.card.quote?.includes("retinal illuminance"));
});

test("tool chips carry plain labels and results point at panels", () => {
  const tools = live.filter((e) => e.kind === "tool");
  assert.ok(tools.length >= 3);
  for (const t of tools) assert.ok(t.kind === "tool" && t.label && !t.label.includes("{"));
  const done = live.filter((e) => e.kind === "tool_done");
  const claim = done.map((d) => (d.kind === "tool_done" ? panelFor(d.refs) : null)).find(Boolean);
  assert.deepEqual(claim, { panel: "claim", id: "lib:felidae.senses.vision.detection_threshold" });
});

test("the turn ends with done and the pending action id", () => {
  const ends = live.filter((e) => e.kind === "done");
  assert.equal(ends.length, 2);
  const last = ends[1];
  assert.ok(last.kind === "done" && last.stop === "pending_action" && last.pending.length === 1);
});

test("a stored transcript replays as the same events", () => {
  const items = transcriptEvents(rec.transcript as never);
  assert.equal(items.length, rec.transcript.length);
  assert.ok(items.some((i) => i.kind === "user"));
  const card = items.find((i) => i.kind === "card");
  assert.ok(card && card.kind === "card" && card.card.id.startsWith("act-"));
});

test("actionCard accepts the action itself and tolerates missing fields", () => {
  assert.equal(actionCard({ id: "a1", kind: "new_claim", card: {} }).id, "a1");
  const bare = actionCard({});
  assert.equal(bare.title, "Proposed change");
  assert.deepEqual(bare.rows, []);
});

test("errors and progress", () => {
  assert.deepEqual(chatEvent("error", '{"message":"m","code":"unverified_number"}'), { kind: "error", message: "m", code: "unverified_number" });
  assert.deepEqual(chatEvent("job_progress", '{"job_id":"j","frac":0.5,"message":"running"}'), { kind: "progress", frac: 0.5, message: "running" });
  assert.deepEqual(chatEvent("something_new", "{}"), { kind: "ignored", name: "something_new" });
});

test("the start screen is narrowed to the clade, this sense first", () => {
  const s = startFor(
    {
      least_verified: [
        { claim_id: "a", library_path: "felidae.senses.hearing.x", value: "", status: "unverified", why: "", species: null, read_by: [] },
        { claim_id: "b", library_path: "strigidae.senses.vision.y", value: "", status: "unverified", why: "", species: null, read_by: [] },
        { claim_id: "c", library_path: "felidae.senses.vision.z", value: "", status: "unverified", why: "", species: null, read_by: [] },
      ],
      open_questions: [
        { hypothesis_id: "hyp:request:felidae-vision-q-1", statement: "", priority: "high", target: null, read_by: [] },
        { hypothesis_id: "hyp:open_question:strigidae.senses.hearing#1", statement: "", priority: "low", target: "strigidae.senses.hearing", read_by: [] },
      ],
    },
    "felidae",
    "vision",
  );
  assert.deepEqual(s.values.map((v) => v.claim_id), ["c", "a"]);
  assert.deepEqual(s.questions.map((q) => q.hypothesis_id), ["hyp:request:felidae-vision-q-1"]);
});

test("formatting", () => {
  assert.equal(pct(0.667), "67%");
  assert.equal(pct(null), "—");
  assert.equal(arrow(0.5, 0.667), "50% → 67%");
});

test("parseSse splits complete events and keeps the rest", () => {
  const { events, rest } = parseSse('event: text_delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\nevent: tool_');
  assert.deepEqual(events, [
    { event: "text_delta", data: '{"text":"a"}' },
    { event: "done", data: "{}" },
  ]);
  assert.equal(rest, "event: tool_");
});
