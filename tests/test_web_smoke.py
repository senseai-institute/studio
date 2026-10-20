# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Browser smoke test: the built web app against a live server on the fixture stack.

Skipped when the web app is not built (``make build``) or Playwright's Chromium is missing.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from senseai_studio.app import STATIC, create_app
from senseai_studio.settings import Settings
from tests.test_runs import dsec_fixture

sync_api = pytest.importorskip("playwright.sync_api")
CHROMIUM = os.environ.get("STUDIO_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
pytestmark = pytest.mark.skipif(not (STATIC / "index.html").is_file(), reason="web app not built")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def server(cfg: Settings) -> Iterator[tuple[str, Settings]]:
    dsec_fixture(cfg.data_root)  # type: ignore[arg-type]
    port = _port()
    srv = uvicorn.Server(
        uvicorn.Config(create_app(cfg), host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", cfg
    srv.should_exit = True
    t.join(5)


@pytest.fixture
def page(server: tuple[str, Settings]) -> Iterator[Any]:
    with sync_api.sync_playwright() as p:
        kw = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
        try:
            b = p.chromium.launch(**kw)
        except Exception as e:  # no browser on this machine
            pytest.skip(f"no chromium: {e}")
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg
        b.close()
        assert not errors, errors


def test_home_to_every_tab(server: tuple[str, Settings], page: Any) -> None:
    url, _ = server
    pg = page
    pg.goto(f"{url}/")
    pg.wait_for_selector(".species-card")
    assert pg.url.endswith("/studio")
    chip = pg.locator('[data-clade="felidae"] a[data-sense="vision"]')
    assert "MODELLED" in chip.inner_text().upper()
    chip.click()
    pg.wait_for_selector(".quantity")
    q = pg.locator('[data-path="felidae.senses.vision.detection_threshold"]')
    assert "-0.74" in q.inner_text() and "UNVERIFIED" in q.inner_text().upper()
    assert "doi.org/10.1152/jn.90641.2008" in q.locator("a").first.get_attribute("href")
    assert "profiles/library/felidae.yaml:" in q.inner_text()
    step = pg.locator('[data-testid="pipeline-step"]')
    assert "3/10" in step.inner_text()
    for tab, sel, text in [
        ("model", ".panel", "UNTRAINED"),
        ("pipeline", ".checklist", "1 OF 2 ROWS VERIFIED"),
        ("use-cases", ".markdown", "STEP 3/10"),
        ("run", ".choices", "SYNTHETIC"),
        ("sources", ".quantity", "CONFIDENCE"),
    ]:
        pg.click(f'.tabs a[data-tab="{tab}"]')
        pg.wait_for_selector(sel)
        assert text in pg.locator(".tab-body").inner_text().upper(), tab
    assert pg.locator('.tabs a[data-tab="research"]').count() == 0


def _run(pg: Any, url: str, path: str, source: str | None = None) -> str:
    pg.goto(f"{url}/studio/{path}/run")
    pg.wait_for_selector(".choices")
    if source:
        pg.check(f'input[name="source"][value="{source}"]')
    pg.click("button.btn.primary")
    pg.wait_for_selector("[data-status]", timeout=30000)
    return str(pg.locator(".tab-body").inner_text())


@pytest.mark.parametrize("path", ["felidae/vision", "strigidae/hearing"])
def test_synthetic_run_streams(server: tuple[str, Settings], page: Any, path: str) -> None:
    url, _ = server
    text = _run(page, url, path)
    assert "Synthetic data: shows the pipeline, not a result." in text
    assert "Not pre-registered" in text
    assert page.locator(".feed li").count() >= 1
    assert "SUCCEEDED" in text.upper()


def test_dsec_run_draws_ring_over_frames(server: tuple[str, Settings], page: Any) -> None:
    url, _ = server
    text = _run(page, url, "felidae/vision", "dsec:zurich_city_fixture")
    assert "Synthetic data" not in text.split("Live")[-1]
    assert int(page.locator(".live").get_attribute("data-frames") or 0) >= 1
    assert page.locator(".live-stage img.frame").get_attribute("src")
    lit = page.evaluate(
        "() => { const c = document.querySelector('canvas.ring');"
        " const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
        " let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; }"
    )
    assert lit > 100  # the ring and the fire marker were drawn


def test_research_tab_when_configured(cfg: Settings) -> None:
    c = replace(cfg, research_url="http://127.0.0.1:9")
    from fastapi.testclient import TestClient

    assert TestClient(create_app(c)).get("/api/studio/health").json()["research"]["configured"]


@pytest.fixture
def research_server() -> Iterator[str]:
    from tests.fake_research import make_app

    port = _port()
    srv = uvicorn.Server(
        uvicorn.Config(make_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


def test_research_tab_end_to_end(cfg: Settings, research_server: str, page: Any) -> None:
    """Studio → its proxy (with the shared token) → research: what to check, a claim, the chat
    replaying recorded research events, approving a card, and testing an API key."""
    from tests.fake_research import TOKEN

    c = replace(cfg, research_url=research_server, research_token=TOKEN)
    port = _port()
    srv = uvicorn.Server(
        uvicorn.Config(create_app(c), host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{port}/studio/felidae/vision/research")
        pg.wait_for_selector(".start-row")
        rows = pg.locator(".start-row")
        assert rows.count() == 1, "only this clade's values"
        assert "What is the cat's scotopic" in pg.locator(".start").inner_text()
        rows.first.click()
        pg.wait_for_selector(".claim-value")
        assert pg.locator(".claim-value").inner_text() == "-0.74 log10 re human"

        pg.fill(".chat-form textarea", "Where does -0.74 come from?")
        pg.click(".chat-form button[type=submit]")
        pg.wait_for_selector('.tool-chip[data-state="ok"]')
        pg.wait_for_function("() => !document.querySelector('.chat-form button').disabled")
        assert "{" not in pg.locator(".chat").inner_text(), "no raw JSON in the chat"
        assert pg.locator(".msg.assistant").count() >= 1

        pg.fill(".chat-form textarea", "Use the optics-removed value.")
        pg.click(".chat-form button[type=submit]")
        card = pg.locator('.action-card[data-status="pending"]')
        card.wait_for()
        assert card.get_attribute("data-action", timeout=1000).startswith("act-")
        assert "-0.08" in card.inner_text()
        card.get_by_role("button", name="Approve").click()
        assert "full sentence" in card.locator(".card-status").inner_text()
        card.locator("textarea").fill("For a camera the lens replaces the pupil.")
        card.get_by_role("button", name="Approve").click()
        pg.wait_for_selector('.action-card[data-status="approved"]')
        pg.wait_for_function(
            "() => document.querySelector('.claim-value')?.textContent === '-0.08 log10 re human'"
        )

        pg.click("#research-tab-settings")
        pg.wait_for_selector(".settings-table")
        assert pg.locator('tr[data-service="openalex"]').get_attribute("data-state") == "not_set"
        pg.locator('tr[data-service="openalex"]').get_by_role("button", name="Test").click()
        pg.wait_for_selector('tr[data-service="openalex"] .check-result[data-ok="true"]')
        assert "Railway" in pg.locator(".settings-view").inner_text()
        if shots := os.environ.get("STUDIO_SCREENSHOTS"):
            pg.screenshot(path=f"{shots}/research-settings.png")
            pg.click("#research-tab-claim")
            pg.screenshot(path=f"{shots}/research-claim.png")
    finally:
        srv.should_exit = True
        t.join(5)
