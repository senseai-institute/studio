// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
import { test } from "node:test";
import assert from "node:assert/strict";
import { dataLabel, day, ms, pct, short, slotLabel, step, value, whereLabel } from "./format.ts";

test("whereLabel", () => {
  assert.equal(whereLabel({ source_file: "profiles/library/x.yaml", line_or_key: 27 }), "profiles/library/x.yaml:27");
  assert.equal(whereLabel({ source_file: "cli:k", line_or_key: "knob" }), "cli:k · knob");
  assert.equal(whereLabel({ source_file: "f", line_or_key: null }), "f");
});

test("value", () => {
  assert.equal(value(-0.74), "-0.74");
  assert.equal(value([48, 85000]), "48–85,000");
  assert.equal(value(460000), "460,000");
  assert.equal(value("x"), "x");
});

test("step and day", () => {
  assert.equal(step(3, 10), "step 3/10");
  assert.equal(step(null, 10), "step —");
  assert.equal(day("2026-10-17T16:43:06-04:00"), "2026-10-17");
  assert.equal(day(null), "—");
});

test("labels", () => {
  assert.equal(dataLabel("synthetic"), "synthetic only");
  assert.equal(slotLabel("latency_ms"), "latency");
  assert.equal(slotLabel("acoustic_orienting.latency_ms"), "acoustic orienting · latency ms");
  assert.equal(short("abcdef0123456789"), "abcdef012345…");
  assert.equal(ms(9.46), "9.5 ms");
  assert.equal(ms(null), "—");
  assert.equal(pct(0.5), "50%");
});
