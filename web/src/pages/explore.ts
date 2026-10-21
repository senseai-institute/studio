// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
//
// Explore: any species, whether or not the library has it.
//   /studio/explore?q=leopard        taxa with that name (GBIF)
//   /studio/explore/{key}            the taxon's senses, ranked by how many papers cover each
//   /studio/explore/{key}/{sense}    those papers, and the research assistant's summary
// Names and papers come from /api/studio/explore/*; the summary from the research service.

import { api, type ExplorePapers, type LibraryLink, type Paper, type SenseHits, type Taxon } from "../api.ts";
import { badge, el, empty, errorBox, inspect, link, section, sourceChip, tags } from "../dom.ts";
import { chatEvent, transcriptEvents, type ChatEvent } from "../research/adapt.ts";
import { research } from "../research/client.ts";
import { shell } from "../shell.ts";

const SOURCE = { openalex: "OpenAlex", europepmc: "Europe PMC" } as const;
const FALLBACK = "OpenAlex is limiting requests right now, so these come from Europe PMC (life-science papers only). Set OPENALEX_API_KEY on Studio for a larger OpenAlex allowance.";

const name = (t: Taxon): string => t.common_names[0] ?? t.scientific_name ?? String(t.key);
const lineage = (t: Taxon): string =>
  ["class", "order", "family", "genus"].map((k) => t.classification[k]).filter(Boolean).join(" › ");

/** The big "any species" box, on Home and on every Explore page. */
export function speciesSearch(value = ""): HTMLFormElement {
  const f = el("form", "explore-search");
  f.action = "/studio/explore";
  f.method = "get";
  f.setAttribute("role", "search");
  const input = el("input");
  input.name = "q";
  input.type = "search";
  input.required = true;
  input.minLength = 2;
  input.value = value;
  input.placeholder = "Any animal: leopard, barn owl, Octopus vulgaris…";
  input.setAttribute("aria-label", "Search any species");
  const go = el("button", "btn primary", "Search");
  go.type = "submit";
  f.append(input, go);
  return f;
}

function header(eyebrow: string, title: Node | string, lede?: string): HTMLElement {
  const h = el("header", "explore-head");
  const h1 = el("h1", "page-title");
  h1.append(title);
  h.append(el("div", "eyebrow", eyebrow), h1);
  if (lede) h.append(el("p", "lede", lede));
  return h;
}

function titleOf(t: Taxon, extra?: string): HTMLElement {
  const s = el("span");
  s.append(extra ? `${name(t)} · ${extra}` : name(t));
  if (t.common_names.length && t.scientific_name) s.append(el("span", "latin", t.scientific_name));
  return s;
}

function libraryNote(lib: LibraryLink | null, sense?: { id: string; state: string } | null): HTMLElement | null {
  if (!lib) return null;
  const p = el("p", "note");
  if (sense) {
    p.append(`${lib.name} → ${sense.id} is in the library (${sense.state}). `, link("Open the workspace", `/studio/${encodeURIComponent(lib.clade)}/${encodeURIComponent(sense.id)}`), " for its cited values, model and runs.");
  } else {
    p.append(`This taxon falls under the library entry ${lib.name}. `, link("Open it", `/studio/${encodeURIComponent(lib.clade)}`), ".");
  }
  return p;
}

// ------------------------------------------------------------------ results

async function resultsPage(root: HTMLElement, q: string): Promise<void> {
  const { page } = await shell(root, [["Atlas", "/studio"], ["Explore", null]]);
  page.append(header("Explore · any species", q ? `Species called “${q}”` : "Search any species", "Names come from GBIF's backbone taxonomy, so this covers species the library has no entry for yet."), speciesSearch(q));
  if (!q) return;
  const list = el("div", "taxa");
  list.append(el("p", "loading muted", "Searching GBIF…"));
  page.append(list);
  try {
    const res = await api.exploreSpecies(q);
    list.replaceChildren();
    if (!res.taxa.length) list.append(empty(`GBIF has no animal named “${q}”. Try the scientific name or a broader name.`));
    res.taxa.forEach((t, i) => {
      const a = el("a", "taxon");
      a.href = `/studio/explore/${t.key}`;
      a.dataset.key = String(t.key);
      const top = el("div", "taxon-name");
      top.append(el("strong", undefined, name(t)));
      if (t.common_names.length && t.scientific_name) top.append(el("span", "latin", t.scientific_name));
      top.append(tags(badge(t.rank ?? "taxon", "plain"), t.library ? badge(`in the library: ${t.library.name}`, "teal") : badge("not in the library", "muted")));
      a.append(top, el("div", "faint small", lineage(t)));
      if (t.common_names.length > 1) a.append(el("div", "faint small", `also: ${t.common_names.slice(1).join(", ")}`));
      a.append(sourceChip(res, `taxa/${i}`));
      list.append(a);
    });
    page.append(inspect(res));
  } catch (e) {
    list.replaceChildren(errorBox(e));
  }
}

// ------------------------------------------------------------------ senses

function senseRow(key: number, s: SenseHits, max: number, res: Parameters<typeof sourceChip>[0], i: number): HTMLElement {
  const a = el("a", "sense-row");
  a.href = `/studio/explore/${key}/${encodeURIComponent(s.id)}`;
  a.dataset.sense = s.id;
  const bar = el("span", "bar");
  const fill = el("i");
  fill.style.width = `${s.count ? Math.max(4, (100 * Math.log10(1 + s.count)) / Math.log10(1 + max)) : 0}%`;
  bar.append(fill);
  const count = el("span", "count mono", s.count === null ? "—" : s.count.toLocaleString());
  count.title = s.error ?? `${SOURCE[s.source]} papers matching ${s.filter}`;
  const label = el("span", "label");
  label.append(el("strong", undefined, s.label));
  if (s.library) label.append(" ", badge(s.library.state, s.library.state === "modelled" ? "teal" : "plain", "this sense is in the library"));
  const top = el("span", "top faint small", s.top[0]?.title ? `most cited: ${s.top[0].title}${s.top[0].year ? ` (${s.top[0].year})` : ""}` : s.error ?? "");
  a.append(label, bar, count, top, sourceChip(res, `senses/${i}/count`));
  return a;
}

async function taxonPage(root: HTMLElement, key: number): Promise<void> {
  const { page } = await shell(root, [["Atlas", "/studio"], ["Explore", "/studio/explore"], [String(key), null]]);
  const holder = el("div", "explore");
  holder.append(el("p", "loading muted", "Finding the senses studied in this animal…"));
  page.append(holder);
  try {
    const res = await api.exploreTaxon(key);
    const t = res.taxon;
    document.title = `${name(t)} · Explore · SenseAI Studio`;
    const crumbs = document.querySelector(".crumbs span:last-child");
    if (crumbs) crumbs.textContent = name(t);
    holder.replaceChildren(header(`${t.rank ?? "taxon"} · ${lineage(t)}`, titleOf(t), "Each sense, ranked by how many papers name this animal and the sense in their title or abstract. Open one to read them."));
    const lib = libraryNote(t.library);
    if (lib) holder.append(lib);
    const found = res.senses.filter((s) => s.count);
    const none = res.senses.filter((s) => !s.count);
    const max = Math.max(1, ...found.map((s) => s.count ?? 0));
    const sec = section("", "Senses with published research");
    sec.tools.append(tags(badge(`${found.length} of ${res.senses.length} senses`, "plain"), link("GBIF record", t.gbif, true)));
    const rows = el("div", "sense-rows");
    res.senses.forEach((s, i) => {
      if (s.count) rows.append(senseRow(key, s, max, res, i));
    });
    if (!found.length) rows.append(empty("No papers found for any sense. Try the genus or family instead."));
    sec.body.append(rows);
    if (none.length) {
      const d = el("details", "no-papers");
      d.append(el("summary", undefined, `No papers found: ${none.map((s) => s.label).join(", ")}`));
      const r2 = el("div", "sense-rows");
      res.senses.forEach((s, i) => {
        if (!s.count) r2.append(senseRow(key, s, max, res, i));
      });
      d.append(r2);
      sec.body.append(d);
    }
    const used = [...new Set(res.senses.filter((s) => !s.error).map((s) => SOURCE[s.source]))];
    if (res.senses.some((s) => s.source === "europepmc")) sec.body.prepend(el("p", "note warn", FALLBACK));
    sec.body.append(el("p", "faint small", `Names searched: ${t.query ?? ""}. Sense terms: studio/content/senses.yaml. Papers: ${used.join(", ") || "none"}.`));
    holder.append(sec.box, inspect(res));
  } catch (e) {
    holder.replaceChildren(errorBox(e));
  }
}

// ------------------------------------------------------------------ papers

function years(res: ExplorePapers): HTMLElement {
  const box = el("div", "years");
  const max = Math.max(1, ...res.years.map((y) => y.count));
  const from = res.years[0]?.year;
  const to = res.years[res.years.length - 1]?.year;
  for (const y of res.years) {
    const b = el("i");
    b.style.height = `${Math.max(2, (100 * y.count) / max)}%`;
    b.title = `${y.year}: ${y.count} paper(s)`;
    box.append(b);
  }
  const wrap = el("figure", "years-fig");
  const cap = el("figcaption", "faint small", from ? `Papers per year, ${from}–${to}` : "No dated papers");
  wrap.append(box, cap);
  return wrap;
}

function paperItem(p: Paper): HTMLElement {
  const li = el("li", "paper");
  const h = el("div", "paper-title");
  const href = p.doi ?? p.id;
  h.append(href ? link(p.title ?? "(untitled)", href, true) : (p.title ?? "(untitled)"));
  const meta = el("div", "paper-meta small");
  const authors = p.authors.join(", ") + (p.more_authors ? ` + ${p.more_authors} more` : "");
  meta.append(
    el("span", undefined, authors || "authors not recorded"),
    el("span", "faint", [p.venue, p.year].filter(Boolean).join(", ")),
    tags(badge(`cited ${p.cited_by.toLocaleString()}×`, "plain"), p.type && p.type !== "article" ? badge(p.type, "muted") : null, p.open_access ? badge("free full text", "teal") : null),
  );
  li.append(h, meta);
  const extra = el("div", "paper-links small");
  if (p.open_access) extra.append(link("Read it free", p.open_access, true));
  if (p.doi) extra.append(link(p.doi.replace(/^https:\/\/doi.org\//, "doi:"), p.doi, true));
  li.append(extra);
  if (p.abstract) {
    const d = el("details", "paper-abstract");
    d.append(el("summary", undefined, "Abstract"), el("p", undefined, p.abstract));
    li.append(d);
  }
  return li;
}

/** The research assistant's summary of what is published, streamed from the research service. */
function assistant(t: Taxon, sense: ExplorePapers["sense"]): HTMLElement {
  const sec = section("", "Summary by the research assistant");
  sec.box.classList.add("explore-assistant");
  sec.tools.append(badge("written by the research service, check it against the papers", "muted"));
  const log = el("div", "chat");
  log.setAttribute("aria-live", "polite");
  const go = el("button", "btn primary", "Summarise this research");
  go.type = "button";
  sec.body.append(log, go);
  const focus = t.library && sense.library ? { library_path: `${t.library.clade}.senses.${sense.library.id}` } : null;
  const who = t.common_names[0] ? `${t.scientific_name} (${t.common_names[0]})` : t.scientific_name;
  const prompt = `What does the published research say about ${sense.label.toLowerCase()} in ${who}? Search the literature, then summarise the main findings, with numbers where papers report them and the paper each one comes from. End with what is still unknown.`;
  const key = `explore:conversation:${t.key}:${sense.id}`;
  let reply: HTMLElement | null = null;
  const chips = new Map<string, HTMLElement>();

  const render = (e: ChatEvent | { kind: "user" | "note"; text: string }): void => {
    if (e.kind === "text") {
      reply ??= log.appendChild(el("div", "msg assistant"));
      reply.textContent += e.text;
    } else if (e.kind === "tool") {
      const c = badge(e.label, "muted");
      c.classList.add("tool-chip");
      c.dataset.state = "running";
      chips.set(e.id, c);
      log.append(c);
      reply = null;
    } else if (e.kind === "tool_done") {
      const c = chips.get(e.id);
      if (c) {
        c.dataset.state = e.ok ? "ok" : "problem";
        c.title = e.summary;
      }
    } else if (e.kind === "error") log.append(el("p", "error", e.message));
    else if (e.kind === "note") log.append(el("div", "msg note", e.text));
    else if (e.kind === "user") reply = null;
  };

  const store = (v?: string): string | null => {
    try {
      if (v) sessionStorage.setItem(key, v);
      return sessionStorage.getItem(key);
    } catch {
      return v ?? null;
    }
  };

  void api.health().then(
    async (h) => {
      if (!h.research.configured) {
        go.disabled = true;
        go.title = "Set RESEARCH_URL on Studio to connect the research service";
        log.append(empty("The research service is not connected (RESEARCH_URL is unset), so there is no summary. The papers below are the research."));
        return;
      }
      const old = store();
      if (!old) return;
      try {
        const tr = await research.conversation(old);
        for (const e of transcriptEvents(tr.items)) render(e);
        if (tr.items.length) go.textContent = "Ask again";
      } catch {
        /* the conversation is gone: start a new one on click */
      }
    },
    () => undefined,
  );

  go.addEventListener("click", async () => {
    go.disabled = true;
    log.replaceChildren(el("p", "loading muted", "The assistant is searching the literature…"));
    reply = null;
    try {
      const { id } = await research.newConversation();
      store(id);
      log.replaceChildren();
      for await (const ev of research.send(id, prompt, focus)) render(chatEvent(ev.event, ev.data));
      go.textContent = "Ask again";
    } catch (e) {
      log.append(errorBox(e));
    } finally {
      go.disabled = false;
    }
  });
  return sec.box;
}

async function sensePage(root: HTMLElement, key: number, sense: string): Promise<void> {
  const params = new URLSearchParams(location.search);
  const sort = params.get("sort") === "recent" ? "recent" : "cited";
  const pageNo = Math.max(1, Number(params.get("page")) || 1);
  const { page } = await shell(root, [["Atlas", "/studio"], ["Explore", "/studio/explore"], [String(key), `/studio/explore/${key}`], [sense, null]]);
  const holder = el("div", "explore");
  holder.append(el("p", "loading muted", "Collecting the papers…"));
  page.append(holder);
  try {
    const res = await api.explorePapers(key, sense, sort, pageNo);
    const t = res.taxon;
    document.title = `${name(t)} · ${res.sense.label} · SenseAI Studio`;
    const crumb = document.querySelectorAll(".crumbs a")[2];
    if (crumb) crumb.textContent = name(t);
    holder.replaceChildren(header(`${t.rank ?? "taxon"} · ${lineage(t)}`, titleOf(t, res.sense.label)));
    const lib = libraryNote(t.library, res.sense.library);
    if (lib) holder.append(lib);
    holder.append(assistant(t, res.sense));

    const sec = section("", "Published research");
    const toggle = el("div", "seg");
    for (const [id, label] of [["cited", "Most cited"], ["recent", "Newest"]] as const) {
      const a = link(label, `?sort=${id}`);
      if (id === res.sort) a.setAttribute("aria-current", "true");
      toggle.append(a);
    }
    sec.tools.append(badge(`${res.total.toLocaleString()} papers`, "plain"), toggle);
    if (res.source === "europepmc") sec.body.append(el("p", "note warn", FALLBACK));
    if (res.years.length) sec.body.append(years(res));
    const ol = el("ol", "papers");
    ol.start = (res.page - 1) * res.per_page + 1;
    for (const p of res.papers) ol.append(paperItem(p));
    if (!res.papers.length) sec.body.append(empty("No papers name this animal and this sense in their title or abstract."));
    sec.body.append(ol);
    const pages = res.pages;
    if (pages > 1) {
      const nav = el("nav", "pager");
      if (res.page > 1) nav.append(link("← Previous", `?sort=${res.sort}&page=${res.page - 1}`));
      nav.append(el("span", "faint small", `page ${res.page} of ${pages.toLocaleString()}`));
      if (res.page < pages) nav.append(link("Next →", `?sort=${res.sort}&page=${res.page + 1}`));
      sec.body.append(nav);
    }
    const q = el("p", "faint small");
    q.append(`${SOURCE[res.source]} query: `, el("code", "mono", res.filter));
    sec.body.append(q);
    holder.append(sec.box, inspect(res));
  } catch (e) {
    holder.replaceChildren(errorBox(e));
  }
}

export function explorePage(root: HTMLElement, key?: string, sense?: string): Promise<void> {
  if (!key) return resultsPage(root, new URLSearchParams(location.search).get("q")?.trim() ?? "");
  const k = Number(key);
  if (!Number.isInteger(k)) return resultsPage(root, key);
  return sense ? sensePage(root, k, sense) : taxonPage(root, k);
}
