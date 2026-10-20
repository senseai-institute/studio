// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Router. Plain links and full page loads; every page keeps its state in the URL.
//   /studio                         Home: species × sense
//   /studio/{clade}/{sense}[/{tab}] Workspace; tab is sources | model | run | pipeline | use-cases | research

import "./theme.css";
import "./studio.css";
import { el } from "./dom.ts";
import { homePage } from "./pages/home.ts";
import { workspacePage, TABS, type TabId } from "./pages/workspace.ts";

async function route(root: HTMLElement): Promise<void> {
  const parts = location.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "studio") {
    location.replace("/studio");
    return;
  }
  const [, clade, sense, tab] = parts;
  if (!clade) return homePage(root);
  if (clade && sense) {
    const t = (TABS.find((x) => x.id === tab)?.id ?? "sources") as TabId;
    return workspacePage(root, clade, sense, t);
  }
  root.replaceChildren(el("main", "loading", "Page not found."));
}

const root = document.getElementById("app")!;
root.append(el("div", "loading", "loading…"));
route(root).catch((e: unknown) => {
  root.replaceChildren(el("main", "loading error", `Could not load: ${e instanceof Error ? e.message : String(e)}`));
});
