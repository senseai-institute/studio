// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Pipeline: the ten steps as a checklist with dates, and the pipeline clock.

import type { Pipeline } from "../api.ts";
import { badge, el, from, inspect, panel } from "../dom.ts";
import { day, step } from "../format.ts";

export function pipelineTab(body: HTMLElement, res: Pipeline): void {
  body.replaceChildren();
  const p = panel(`Pipeline · ${step(res.at, res.total)}`);
  const clock = el("p", "clock");
  if (res.clock.days !== null) clock.append(el("b", undefined, `${res.clock.days} day(s)`), ` since step 1 (${day(res.clock.since)})`);
  else clock.append(el("span", "muted", "Clock not started: step 1 has no date yet."));
  if (res.clock.partial) clock.append(" ", badge("partial", "warn", res.clock.out_of_order ? "a later step is done while an earlier one is not" : "step 1 has no date"));
  p.head.append(res.complete ? badge("complete", "teal") : badge(`at step ${res.at}`, "muted"));
  p.body.append(clock);
  if (res.species.length) p.body.append(el("p", "muted small", `Species files: ${res.species.join(", ")}`));
  const ol = el("ol", "checklist");
  res.steps.forEach((s, i) => {
    const li = el("li", s.done ? "done" : s.n === res.at ? "current" : "todo");
    li.dataset.step = String(s.n);
    const mark = el("span", "mark", s.done ? "✓" : s.n === res.at ? "●" : "○");
    mark.setAttribute("aria-label", s.done ? "done" : s.n === res.at ? "in progress" : "not done");
    const name = el("span", "name", `${s.n}. ${s.name}`);
    const when = el("span", "when mono", s.done ? day(s.at) : s.n === res.at ? "in progress" : "");
    const detail = el("div", "detail", s.detail);
    if (s.source_file) detail.append(" ", el("span", "src mono", s.source_file));
    li.append(mark, name, when, detail);
    from(li, res, `steps/${i}/done`);
    ol.append(li);
  });
  p.body.append(ol, el("p", "muted small", `Steps and checks: ${res.steps_file}`));
  body.append(p.box, inspect(res));
}
