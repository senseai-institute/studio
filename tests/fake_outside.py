# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Fake GBIF and OpenAlex for Explore: an httpx handler (``httpx.MockTransport(handler)``).

Answers have the real services' shapes (fields Explore reads only). Counts depend on the sense
terms in the filter, so ranking can be checked: vision 412, hearing 57, smell 12, others 0.
"""

from __future__ import annotations

from typing import Any

import httpx

LEOPARD = {
    "key": 5219436,
    "canonicalName": "Panthera pardus",
    "scientificName": "Panthera pardus (Linnaeus, 1758)",
    "authorship": "(Linnaeus, 1758)",
    "rank": "SPECIES",
    "taxonomicStatus": "ACCEPTED",
    "kingdom": "Animalia",
    "phylum": "Chordata",
    "class": "Mammalia",
    "order": "Carnivora",
    "family": "Felidae",
    "genus": "Panthera",
}
FLORIDA = LEOPARD | {
    "key": 7193927,
    "canonicalName": "Puma concolor coryi",
    "rank": "SUBSPECIES",
    "genus": "Puma",
}
NAMES = {
    5219436: [
        {"vernacularName": "Leopard", "language": "eng"},
        {"vernacularName": "Panther", "language": "eng"},
        {"vernacularName": "Léopard", "language": "fra"},
        {"vernacularName": "leopard", "language": "eng"},
    ],
    7193927: [{"vernacularName": "Florida panther", "language": "eng"}],
}
COUNTS = {"vision": 412, "hearing": 57, "olfaction": 12}
SEEN: list[httpx.Request] = []


def work(i: int, sense: str) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/W{1000 + i}",
        "doi": f"https://doi.org/10.1000/{sense}.{i}",
        "title": f"The {sense} of the leopard, part {i}",
        "publication_year": 2020 - i,
        "type": "article",
        "cited_by_count": 300 - i,
        "authorships": [{"author": {"display_name": f"Author {j}"}} for j in range(8)],
        "primary_location": {"source": {"display_name": "Journal of Felid Biology"}},
        "open_access": {"is_oa": i % 2 == 0, "oa_url": f"https://example.org/{i}.pdf"},
        "abstract_inverted_index": {"Leopards": [0], "see": [1], "well": [2]},
    }


def handler(request: httpx.Request) -> httpx.Response:
    SEEN.append(request)
    path, q = request.url.path, request.url.params
    if path == "/v1/species/search":
        hits = [
            t | {"vernacularNames": NAMES[t["key"]]}
            for t in (LEOPARD, FLORIDA)
            if q.get("q", "").lower()
            in " ".join(n["vernacularName"].lower() for n in NAMES[t["key"]])
        ]
        return httpx.Response(200, json={"results": hits})
    if path == "/v1/species/suggest":
        genus = {
            "key": 2435194,
            "canonicalName": "Panthera",
            "rank": "GENUS",
            "kingdom": "Animalia",
            "family": "Felidae",
            "order": "Carnivora",
            "class": "Mammalia",
        }
        return httpx.Response(
            200, json=[genus] if q.get("q", "").lower().startswith("panther") else []
        )
    for t in (LEOPARD, FLORIDA):
        if path == f"/v1/species/{t['key']}":
            return httpx.Response(200, json=t)
        if path == f"/v1/species/{t['key']}/vernacularNames":
            return httpx.Response(200, json={"results": NAMES[t["key"]]})
    if path.startswith("/v1/species/"):
        return httpx.Response(404, json={})
    if path == "/works":
        flt = q.get("filter", "")
        sense = next(
            (
                s
                for s, w in (
                    ("vision", "retina"),
                    ("hearing", "auditory"),
                    ("olfaction", "olfactory"),
                )
                if w in flt
            ),
            None,
        )
        n = COUNTS.get(sense or "", 0)
        if "group_by" in q:
            return httpx.Response(
                200,
                json={
                    "group_by": [
                        {"key": "2019", "count": n // 2},
                        {"key": "2021", "count": n - n // 2},
                    ]
                },
            )
        per = int(q.get("per-page", "25"))
        return httpx.Response(
            200,
            json={
                "meta": {"count": n},
                "results": [work(i, sense or "x") for i in range(min(n, per))],
            },
        )
    return httpx.Response(404, json={})
