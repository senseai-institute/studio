// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSse } from "./research.ts";

test("parseSse splits complete events and keeps the rest", () => {
  const { events, rest } = parseSse('event: text_delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\nevent: tool_');
  assert.deepEqual(events, [
    { event: "text_delta", data: '{"text":"a"}' },
    { event: "done", data: "{}" },
  ]);
  assert.equal(rest, "event: tool_");
});

test("parseSse joins multi-line data and defaults the event name", () => {
  const { events } = parseSse("data: one\ndata: two\n\n");
  assert.deepEqual(events, [{ event: "message", data: "one\ntwo" }]);
});
