// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Page chrome: the top bar, after the viewer's (same tokens, same brand mark).

import { el } from "./dom.ts";

export function topbar(title = "", crumbs: [string, string][] = []): HTMLElement {
  const bar = el("header", "topbar");
  const brand = el("a", "brand");
  brand.href = "/studio";
  brand.append(el("span", "brand-mark"), "SenseAI Studio");
  bar.append(brand);
  if (crumbs.length) {
    const nav = el("nav");
    nav.setAttribute("aria-label", "Breadcrumbs");
    for (const [label, href] of crumbs) {
      const a = el("a", undefined, label);
      a.href = href;
      nav.append(a);
    }
    bar.append(nav);
  }
  bar.append(el("span", "title", title));
  return bar;
}
