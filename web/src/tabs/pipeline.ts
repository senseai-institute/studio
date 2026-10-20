// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Pipeline: the ten steps as a timeline with dates and the evidence behind each, and the clock.

import type { Pipeline } from "../api.ts";
import { badge, el, from, inspect, section, srcRef, tags } from "../dom.ts";
import { day } from "../format.ts";

export function pipelineTab(body: HTMLElement, res: Pipeline): void {
  body.replaceChildren();
  const s = section("", "Pipeline");
  s.tools.append(tags(
    res.complete ? badge("complete", "teal") : badge(`at step ${res.at} of ${res.total}`, "warn"),
    res.clock.days !== null ? badge(`${res.clock.days} day(s) since step 1`, "plain", `since ${day(res.clock.since)}`) : badge("clock not started", "muted", "step 1 has no date yet"),
    res.clock.partial ? badge("partial", "warn", res.clock.out_of_order ? "a later step is done while an earlier one is not" : "step 1 has no date") : null,
  ));
  if (res.species.length) s.body.append(el("p", "faint small", `Species files read for this sense: ${res.species.join(", ")}`));
  const ol = el("ol", "steps checklist");
  res.steps.forEach((st, i) => {
    const state = st.done ? "done" : st.n === res.at ? "current" : "todo";
    const li = el("li", state);
    li.dataset.step = String(st.n);
    const mark = el("span", "mark", st.done ? "✓" : String(st.n));
    mark.setAttribute("aria-label", st.done ? "done" : state === "current" ? "in progress" : "not done");
    const when = el("span", "when", st.done ? day(st.at) : state === "current" ? "in progress" : "");
    const detail = el("div", "detail");
    detail.append(st.detail);
    if (st.counts) detail.append(" ", badge(`${st.counts.verified}/${st.counts.total}`, st.counts.verified === st.counts.total ? "teal" : "warn"));
    if (st.source_file) detail.append(el("br"), srcRef(st.source_file));
    li.append(mark, el("span", "name", st.name), when, detail);
    from(li, res, `steps/${i}/done`);
    ol.append(li);
  });
  s.body.append(ol, el("p", "faint small", `Steps and how each is checked: ${res.steps_file}`));
  body.append(s.box, inspect(res));
}
