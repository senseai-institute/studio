# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Explore: any species, whether or not the library has it.

    GET /api/studio/explore/species?q=leopard            taxa matching a name (GBIF backbone)
    GET /api/studio/explore/taxon/{key}                  the taxon and its senses, ranked by
                                                         how many papers cover each (OpenAlex)
    GET /api/studio/explore/taxon/{key}/{sense}/papers   those papers, most cited or newest

Names come from GBIF's backbone taxonomy, papers from OpenAlex. Both are public, need no key and
are cached in memory for a few hours. A sense's count is the number of works whose title or
abstract names the taxon (scientific name or an English name) and one of the sense's terms in
``content/senses.yaml``; every count is returned with the exact query it came from. Studio
makes no model call here: summaries are the research service's (the Research tab's chat).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from senseai_studio.facts import content
from senseai_studio.prov import Located, Prov
from senseai_studio.settings import Settings

GBIF = "https://api.gbif.org/v1"
OPENALEX = "https://api.openalex.org"
BACKBONE = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"  # GBIF Backbone Taxonomy
RANKS = ("SPECIES", "SUBSPECIES", "GENUS", "FAMILY", "ORDER", "CLASS")
TTL = 6 * 3600
PER_PAGE = 25
WORK_FIELDS = (
    "id,doi,title,publication_year,type,cited_by_count,authorships,primary_location,"
    "open_access,abstract_inverted_index"
)
SORTS = {"cited": "cited_by_count:desc", "recent": "publication_date:desc"}


class ExploreError(Exception):
    """An outside service failed or answered with something unusable."""


class NotFound(Exception):
    """No such taxon or sense."""


def _quote(term: str) -> str:
    t = term.replace('"', "").replace(",", " ").strip()
    return f'"{t}"' if " " in t or "-" in t else t


def any_of(terms: list[str]) -> str:
    """``(a OR "b c")``: OpenAlex boolean search over the given words and phrases."""
    return "(" + " OR ".join(_quote(t) for t in terms if t.strip()) + ")"


def abstract(idx: dict[str, list[int]] | None, limit: int = 1500) -> str | None:
    """OpenAlex stores abstracts as word -> positions."""
    if not idx:
        return None
    pos = {p: w for w, ps in idx.items() for p in ps}
    text = " ".join(pos[i] for i in sorted(pos))
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def english_names(rows: list[dict[str, Any]]) -> list[str]:
    """English vernacular names, de-duplicated, in GBIF's order."""
    out: list[str] = []
    for r in rows:
        if (r.get("language") or "") not in ("eng", "en", ""):
            continue
        n = str(r.get("vernacularName") or "").strip()
        if n and n.lower() not in {x.lower() for x in out}:
            out.append(n)
    return out


class Explore:
    """Talks to GBIF and OpenAlex, caching answers."""

    def __init__(
        self,
        cfg: Settings,
        library: Any,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cfg = cfg
        self.library = library  # () -> the species() payload (cards), for library links
        self.transport = transport
        self.cache: dict[str, tuple[float, Any]] = {}
        self.sem = asyncio.Semaphore(4)

    # ------------------------------------------------------------------ plumbing

    def senses(self) -> Located:
        """``content/senses.yaml``: each sense and its search terms."""
        return content.senses(self.cfg.content)

    def _openalex_params(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if mail := os.environ.get("SENSEAI_CONTACT_EMAIL"):
            p["mailto"] = mail
        if key := os.environ.get("OPENALEX_API_KEY"):
            p["api_key"] = key
        return p

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        hit = self.cache.get(key)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
        host = "GBIF" if url.startswith(GBIF) else "OpenAlex"
        async with self.sem:
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=20) as c:
                    r = await c.get(url, params=params, headers={"User-Agent": "senseai-studio"})
            except httpx.HTTPError as e:
                raise ExploreError(f"{host} unreachable: {type(e).__name__}") from e
        if r.status_code == 404:
            raise NotFound(f"{host} has no {url.rsplit('/', 1)[-1]}")
        if r.status_code >= 400:
            raise ExploreError(f"{host} answered {r.status_code}")
        data = r.json()
        if len(self.cache) > 1000:
            self.cache.clear()
        self.cache[key] = (time.monotonic(), data)
        return data

    def _library_for(self, taxon: dict[str, Any]) -> dict[str, Any] | None:
        """The library entry covering this taxon (its clade named in GBIF's classification)."""
        names = {
            str(taxon.get(k) or "").lower()
            for k in ("canonicalName", "genus", "family", "order", "class")
        } - {""}
        for card in self.library()["cards"]:
            if {str(card.get("latin") or "").lower(), card["clade"].lower()} & names:
                return {
                    "clade": card["clade"],
                    "name": (card.get("names") or [card["clade"]])[0],
                    "senses": {
                        s["modality"]: {"id": s["id"], "state": s["state"]} for s in card["senses"]
                    },
                }
        return None

    @staticmethod
    def _taxon(t: dict[str, Any], names: list[str]) -> dict[str, Any]:
        return {
            "key": t.get("key"),
            "scientific_name": t.get("canonicalName") or t.get("scientificName"),
            "authorship": t.get("authorship") or None,
            "rank": str(t.get("rank") or "").lower() or None,
            "common_names": names,
            "classification": {
                k: t.get(k) for k in ("kingdom", "phylum", "class", "order", "family", "genus")
            },
            "gbif": f"https://www.gbif.org/species/{t.get('key')}",
        }

    # ------------------------------------------------------------------ species search

    async def species(self, q: str) -> dict[str, Any]:
        """Taxa whose English or scientific name matches ``q``, best first."""
        q = q.strip()
        p = Prov()
        if len(q) < 2:
            return {"query": q, "taxa": [], "provenance": p.out()}
        by_name, suggest = await asyncio.gather(
            self._get(
                f"{GBIF}/species/search",
                {
                    "q": q,
                    "qField": "VERNACULAR",
                    "datasetKey": BACKBONE,
                    "status": "ACCEPTED",
                    "kingdom": "Animalia",
                    "limit": 30,
                },
            ),
            self._get(
                f"{GBIF}/species/suggest",
                {"q": q, "datasetKey": BACKBONE, "status": "ACCEPTED", "limit": 10},
            ),
        )
        rows: dict[int, tuple[dict[str, Any], list[str]]] = {}
        for t in (by_name or {}).get("results", []):
            key = t.get("nubKey") or t.get("key")
            if key is not None:
                rows.setdefault(
                    int(key), ({**t, "key": key}, english_names(t.get("vernacularNames") or []))
                )
        for t in suggest or []:
            if t.get("kingdom") == "Animalia" and t.get("key") is not None:
                rows.setdefault(int(t["key"]), (t, []))
        ql = q.lower()

        def score(item: tuple[dict[str, Any], list[str]]) -> tuple[int, int, int]:
            t, names = item
            lower = [n.lower() for n in names]
            sci = str(t.get("canonicalName") or "").lower()
            exact = (
                0 if ql in lower or ql == sci else 1 if any(ql in n.split() for n in lower) else 2
            )
            rank = RANKS.index(t["rank"]) if t.get("rank") in RANKS else len(RANKS)
            return (exact, rank, -int(t.get("numOccurrences") or 0))

        taxa: list[dict[str, Any]] = []
        for t, names in sorted((x for x in rows.values() if x[0].get("rank") in RANKS), key=score)[
            :12
        ]:
            names = sorted(names, key=lambda n: (ql not in n.lower(), len(n)))[:4]
            row = self._taxon(t, names)
            row["library"] = self._library_for(t)
            p.add(f"taxa/{len(taxa)}", "gbif:species", t["key"])
            taxa.append(row)
        return {"query": q, "taxa": taxa, "provenance": p.out()}

    # ------------------------------------------------------------------ one taxon

    async def _taxon_full(self, key: int) -> dict[str, Any]:
        t, v = await asyncio.gather(
            self._get(f"{GBIF}/species/{key}"),
            self._get(f"{GBIF}/species/{key}/vernacularNames", {"limit": 200}),
        )
        names = english_names((v or {}).get("results", []))[:3]
        row = self._taxon(t, names)
        row["library"] = self._library_for(t)
        terms = [row["scientific_name"], *names]
        row["query"] = any_of([x for x in terms if x])
        return row

    def _sense(self, sense: str) -> tuple[dict[str, Any], int | None]:
        doc = self.senses()
        s = (doc.data or {}).get(sense)
        if not isinstance(s, dict):
            raise NotFound(f"no sense {sense!r} in {doc.label}")
        return s, doc.line(sense)

    def _filter(self, taxon: dict[str, Any], terms: list[str]) -> str:
        return f"title_and_abstract.search:{taxon['query']} AND {any_of(terms)}"

    async def taxon(self, key: int) -> dict[str, Any]:
        """The taxon and each sense with how many papers cover it, most covered first."""
        t = await self._taxon_full(key)
        doc = self.senses()
        p = Prov()
        p.add("taxon", "gbif:species", key)

        async def count(sid: str, s: dict[str, Any]) -> dict[str, Any]:
            terms = [str(x) for x in s.get("terms") or [sid]]
            flt = self._filter(t, terms)
            row: dict[str, Any] = {
                "id": sid,
                "label": s.get("label") or sid,
                "terms": terms,
                "filter": flt,
                "count": None,
                "top": [],
                "error": None,
            }
            try:
                d = await self._get(
                    f"{OPENALEX}/works",
                    {
                        "filter": flt,
                        "per-page": 3,
                        "sort": "cited_by_count:desc",
                        "select": "id,title,publication_year,cited_by_count",
                    }
                    | self._openalex_params(),
                )
            except ExploreError as e:
                row["error"] = str(e)
                return row
            row["count"] = int(((d or {}).get("meta") or {}).get("count") or 0)
            row["top"] = [
                {"title": w.get("title"), "year": w.get("publication_year"), "id": w.get("id")}
                for w in (d or {}).get("results", [])
            ]
            return row

        items = [(k, v) for k, v in (doc.data or {}).items() if isinstance(v, dict)]
        senses = await asyncio.gather(*(count(k, v) for k, v in items))
        if senses and all(s["error"] for s in senses):
            raise ExploreError(senses[0]["error"])
        lib = t["library"]
        for s in senses:
            s["library"] = (lib or {}).get("senses", {}).get(s["id"])
        senses.sort(key=lambda s: (-(s["count"] or 0), s["label"]))
        for i, s in enumerate(senses):
            p.add(f"senses/{i}/terms", doc.label, doc.line(s["id"], "terms"))
            p.add(f"senses/{i}/count", "openalex:works", s["filter"])
        return {"taxon": t, "senses": senses, "provenance": p.out()}

    async def papers(
        self, key: int, sense: str, sort: str = "cited", page: int = 1
    ) -> dict[str, Any]:
        """The papers on one sense of the taxon, a page at a time, and how many per year."""
        s, line = self._sense(sense)
        t = await self._taxon_full(key)
        terms = [str(x) for x in s.get("terms") or [sense]]
        flt = self._filter(t, terms)
        base = self._openalex_params() | {"filter": flt}
        works, years = await asyncio.gather(
            self._get(
                f"{OPENALEX}/works",
                base
                | {
                    "per-page": PER_PAGE,
                    "page": max(page, 1),
                    "sort": SORTS.get(sort, SORTS["cited"]),
                    "select": WORK_FIELDS,
                },
            ),
            self._get(f"{OPENALEX}/works", base | {"group_by": "publication_year"}),
        )
        papers = []
        for w in (works or {}).get("results", []):
            loc = w.get("primary_location") or {}
            src = loc.get("source") or {}
            oa = w.get("open_access") or {}
            authors = [
                str((a.get("author") or {}).get("display_name") or "")
                for a in w.get("authorships") or []
            ]
            papers.append(
                {
                    "id": w.get("id"),
                    "doi": w.get("doi"),
                    "title": w.get("title"),
                    "year": w.get("publication_year"),
                    "type": w.get("type"),
                    "venue": src.get("display_name"),
                    "authors": [a for a in authors if a][:6],
                    "more_authors": max(len(authors) - 6, 0),
                    "cited_by": int(w.get("cited_by_count") or 0),
                    "open_access": oa.get("oa_url") if oa.get("is_oa") else None,
                    "abstract": abstract(w.get("abstract_inverted_index")),
                }
            )
        hist = sorted(
            (
                {"year": int(g["key"]), "count": int(g.get("count") or 0)}
                for g in (years or {}).get("group_by", [])
                if str(g.get("key") or "").isdigit()
            ),
            key=lambda g: g["year"],
        )
        p = Prov()
        p.add("taxon", "gbif:species", key)
        p.add("sense/terms", self.senses().label, line)
        p.add("papers", "openalex:works", flt)
        lib = t["library"]
        return {
            "taxon": t,
            "sense": {
                "id": sense,
                "label": s.get("label") or sense,
                "terms": terms,
                "library": (lib or {}).get("senses", {}).get(sense),
            },
            "filter": flt,
            "sort": sort if sort in SORTS else "cited",
            "page": max(page, 1),
            "per_page": PER_PAGE,
            "total": int(((works or {}).get("meta") or {}).get("count") or 0),
            "papers": papers,
            "years": hist,
            "provenance": p.out(),
        }
