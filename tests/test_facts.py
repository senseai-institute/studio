# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from senseai_studio import studio
from senseai_studio.facts import citations, content, evidence, library
from senseai_studio.facts import profiles as prof
from senseai_studio.prov import load_located
from senseai_studio.settings import Settings


def test_located_yaml_keeps_lines(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("a: 1\nb:\n  - c: 2\n    d: [3, 4]\n")
    doc = load_located(p, "x")
    assert doc.data == {"a": 1, "b": [{"c": 2, "d": [3, 4]}]}
    assert doc.line("a") == 1
    assert doc.line("b", 0, "d") == 4
    assert doc.line("b", 0, "missing") == 3  # nearest parent


def test_library_quantities_and_lines(cfg: Settings) -> None:
    lib = library.load(cfg.profiles)
    c = lib["felidae"]
    qs = c.quantities("vision")
    assert qs[0].path == "felidae.senses.vision.detection_threshold"
    assert qs[0].get("value") == -0.74
    line = c.doc.line(*qs[0].key, "value")
    src = (cfg.profiles / "library/felidae.yaml").read_text().splitlines()
    assert "-0.74" in src[line - 1]
    # behaviours that use the sense bring their quantities
    assert any(
        q.path == "felidae.behaviours.acoustic_orienting.latency_ms"
        for q in c.quantities("hearing")
    )
    assert library.describes(lib["strigidae"], "hearing")
    assert not library.describes(lib["strigidae"], "vision")


def test_citations_parse(cfg: Settings) -> None:
    rows = citations.parse(cfg.profiles / "library/CITATIONS.md")
    r = citations.lookup(rows, "10.1152/jn.90641.2008")
    assert r is not None and r.year == "2009" and r.authors.startswith("Kang")
    assert r.link == "https://doi.org/10.1152/jn.90641.2008"
    assert r.checked == "abstract"
    pmc = citations.lookup(rows, "https://pmc.ncbi.nlm.nih.gov/articles/PMC1350747")
    assert pmc is not None and pmc.doi is None and pmc.year == "1973"
    assert citations.lookup(rows, "10.9999/nothing") is None


def test_fallback_specs_find_consumers(cfg: Settings) -> None:
    specs = prof.load(cfg)
    assert specs.engine == "yaml-fallback"  # the fixture has no senseai-profiles source
    lib = library.load(cfg.profiles)
    assert specs.profiles_reading(lib["felidae"], "vision") == ["panther", "panther_vision"]
    # the panther reflex reads a behaviour that uses hearing
    assert specs.profiles_reading(lib["felidae"], "hearing") == ["panther"]
    assert specs.profiles_reading(lib["strigidae"], "hearing") == []
    assert specs.controls() == ["null"]


def test_evidence_table_and_rulebook(cfg: Settings) -> None:
    t = evidence.table(cfg.profiles, "felidae", "vision")
    assert t.present and t.counts() == (1, 2)
    assert t.for_path("felidae.senses.vision.detection_threshold")[0]["_status"] == "unverified"
    assert not evidence.table(cfg.profiles, "strigidae", "hearing").present
    rb = evidence.rulebook(
        cfg.profiles, [str(cfg.profiles / "rulebook/*.yaml")], "felidae", "vision"
    )
    assert rb["present"] and rb["rules"][0]["status"] == "draft"
    assert rb["rules"][0]["line"] == 3


def test_use_case_templates_and_render(tmp_path: Path) -> None:
    made = content.write_templates(tmp_path, [("felidae", "vision")])
    assert len(made) == 1
    assert content.write_templates(tmp_path, [("felidae", "vision")]) == []
    cases = content.use_cases(tmp_path)
    assert cases[0].is_template and cases[0].meta["status"] == "idea"
    assert content.matching(cases, "felidae", "vision", []) == cases
    assert content.matching(cases, "felidae", "hearing", []) == []
    html = content.render("## Job\n\n- detects <b>x</b>\n")
    assert "<li>" in html and "<b>" not in html  # raw HTML is escaped


def test_pipeline_cats_vision(cfg: Settings) -> None:
    snap = studio.Snapshot.take(cfg)
    pl = studio.pipeline_view(snap, "felidae", "vision")
    steps = {s["id"]: s for s in pl["steps"]}
    assert len(pl["steps"]) == 10
    assert steps["job"]["done"] and "proxy: pedestrians" in steps["job"]["detail"]
    assert steps["sources"]["done"]
    assert not steps["table"]["done"] and steps["table"]["counts"] == {"verified": 1, "total": 2}
    assert not steps["rules"]["done"] and "1 draft" in steps["rules"]["detail"]
    assert steps["prereg"]["done"] and "hash: 3f2a9c" in steps["prereg"]["detail"]
    assert pl["at"] == 3
    assert pl["clock"]["since"] == "2026-10-01" and pl["clock"]["days"] is not None
    assert pl["clock"]["partial"]  # a later step (prereg) is done before the table


def test_pipeline_owls_hearing(cfg: Settings) -> None:
    pl = studio.pipeline_view(studio.Snapshot.take(cfg), "strigidae", "hearing")
    assert pl["at"] == 1 and pl["clock"]["days"] is None
    assert pl["steps"][1]["done"]  # sources found


def test_check_lists_missing(cfg: Settings) -> None:
    rows = {(r["clade"], r["sense"]): r for r in studio.check(studio.Snapshot.take(cfg))}
    owl = rows[("strigidae", "hearing")]
    assert owl["state"] == "described"
    assert "no profile reads this sense" in owl["missing"]
    assert rows[("strigidae", "vision")]["state"] == "empty"
    assert rows[("felidae", "vision")]["state"] == "modelled"
    assert any("1 of 2 rows unverified" in m for m in rows[("felidae", "vision")]["missing"])
