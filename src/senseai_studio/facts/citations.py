# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""``library/CITATIONS.md``: the reference table behind every citation identifier.

Each table row is ``| Identifier | Reference | Used for | Checked |`` under a ``## <Clade>``
heading. An identifier cell holds a DOI, a markdown link, or both (``10.x · [PMC…](url)``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s|·)]+)")
_REF = re.compile(r"^(?P<authors>.+?)\s*\((?P<year>\d{4}[a-z]?)\)\.\s*(?P<rest>.*)$")


@dataclass
class Citation:
    """One row of CITATIONS.md."""

    identifier: str  # the cell as written
    doi: str | None
    urls: list[str]
    reference: str  # the reference cell, verbatim
    authors: str | None
    year: str | None
    title: str | None
    used_for: str
    checked: str
    section: str
    line: int

    @property
    def link(self) -> str | None:
        """DOI resolver link, else the first URL."""
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return self.urls[0] if self.urls else None


def _strip_md(s: str) -> str:
    return re.sub(r"[*_]", "", _LINK.sub(r"\1", s)).strip()


def parse(path: Path) -> list[Citation]:
    """Rows of every table in the file (header and divider rows skipped)."""
    out: list[Citation] = []
    section = ""
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("Identifier", "") or set(cells[0]) <= {"-", " "}:
            continue
        ident, ref, used, checked = cells[:4]
        doi_m = _DOI.search(ident)
        ref_plain = _strip_md(ref)
        m = _REF.match(ref_plain)
        title = None
        if m:
            rest = m["rest"]
            title = rest.split(". ")[0].rstrip(".") if rest else None
        out.append(
            Citation(
                identifier=ident,
                doi=doi_m.group(1).rstrip(".") if doi_m else None,
                urls=[u for _, u in _LINK.findall(ident)],
                reference=ref_plain,
                authors=m["authors"] if m else None,
                year=m["year"] if m else None,
                title=title,
                used_for=used,
                checked=checked,
                section=section,
                line=n,
            )
        )
    return out


def lookup(rows: list[Citation], cite: str) -> Citation | None:
    """The row for a citation identifier as used in a library entry (a DOI or a URL)."""
    c = cite.strip()
    for r in rows:
        if r.doi and r.doi.lower() == c.lower():
            return r
        if c in r.urls:
            return r
    for r in rows:  # a URL cited in the entry may appear only as text in the identifier cell
        if c in r.identifier:
            return r
    return None
