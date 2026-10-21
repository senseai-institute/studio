# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""The Studio server: JSON API under ``/api/studio``, the web app under ``/studio``.

    GET  /api/studio/species                         cards (clade, names, niche, senses)
    GET  /api/studio/{clade}/{sense}/sources         quantities with citations, table, questions
    GET  /api/studio/{clade}/{sense}/model           circuits, profiles, world prior, learned,
                                                     reflex
    GET  /api/studio/{clade}/{sense}/pipeline        steps, the step it is at, the clock
    GET  /api/studio/{clade}/{sense}/use-cases       rendered Markdown + front matter
    GET  /api/studio/{clade}/{sense}/run/options     data sources, arms (with disabled reasons)
    POST /api/studio/{clade}/{sense}/run             start a run -> job
    GET  /api/studio/jobs[?clade=&sense=]            recent runs
    GET  /api/studio/jobs/{id}                       one run (status, summaries, headline)
    POST /api/studio/jobs/{id}/cancel                stop it
    GET  /api/studio/jobs/{id}/events                live events contract (SSE)
    GET  /api/studio/jobs/{id}/report                replay_report.md
    GET  /api/studio/jobs/{id}/files/{path}          a frame image the run wrote
    GET  /api/studio/health                          repos, SHAs, tools, data root
    GET  /api/studio/explore/species?q=              any taxon by name (GBIF)
    GET  /api/studio/explore/taxon/{key}             its senses, ranked by papers (OpenAlex)
    GET  /api/studio/explore/taxon/{key}/{sense}/papers  the papers on one sense
    GET  /api/studio/explore/taxon/{key}/papers?q=   the papers on any sense typed in
    *    /api/studio/research/*                      proxy to RESEARCH_URL (when set)

Every JSON response carries ``provenance``. Studio reads repos read-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel, Field

from senseai_studio import __version__, explore, models, runs, studio
from senseai_studio.auth import BasicAuth
from senseai_studio.facts import upstream
from senseai_studio.research import add_research_routes
from senseai_studio.settings import PACKAGE_DIR, Settings

STATIC = PACKAGE_DIR / "static"
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class RunBody(BaseModel):
    """Body of ``POST /api/studio/{clade}/{sense}/run``."""

    source: str = Field(description="a source id from run/options, e.g. synthetic or dsec:<name>")
    arms: list[str] = Field(min_length=1, description="arm ids from run/options")
    seconds: float = Field(default=runs.DEFAULT_SECONDS, gt=0, le=runs.MAX_SECONDS)


def create_app(cfg: Settings | None = None, **kw: Any) -> Any:
    """Build the ASGI app (wrapped in Basic auth when ``VIEWER_PASSWORD`` is set)."""
    cfg = cfg or Settings.from_env()
    app = FastAPI(
        title="SenseAI Studio",
        version=__version__,
        description="Species sense models: sources, model, run, pipeline, use cases. "
        "Every response carries provenance: [{field, source_file, line_or_key}].",
        openapi_url="/api/studio/openapi.json",
        docs_url="/api/studio/docs",
        redoc_url=None,
    )
    jobs = runs.Jobs(cfg)
    app.state.jobs = jobs
    app.state.cfg = cfg

    def snap(refresh: bool = False) -> studio.Snapshot:
        if refresh:
            upstream.clear()
        return studio.Snapshot.take(cfg)

    def guarded(fn: Any, *a: Any) -> Any:
        try:
            return fn(*a)
        except studio.NotFound as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/studio/health", response_model=models.HealthOut)
    def health(refresh: bool = False) -> Any:
        return studio.health(snap(refresh))

    @app.get("/api/studio/species", response_model=models.SpeciesOut)
    def species(refresh: bool = False) -> Any:
        return studio.species(snap(refresh))

    @app.get("/api/studio/{clade}/{sense}/sources", response_model=models.SourcesOut)
    def sources(clade: str, sense: str) -> Any:
        return guarded(studio.sources, snap(), clade, sense)

    @app.get("/api/studio/{clade}/{sense}/model", response_model=models.ModelOut)
    def model(clade: str, sense: str) -> Any:
        return guarded(studio.model, snap(), clade, sense)

    @app.get("/api/studio/{clade}/{sense}/pipeline", response_model=models.PipelineOut)
    def pipeline(clade: str, sense: str) -> Any:
        return guarded(studio.pipeline_view, snap(), clade, sense)

    @app.get("/api/studio/{clade}/{sense}/use-cases", response_model=models.UseCasesOut)
    def use_cases(clade: str, sense: str) -> Any:
        return guarded(studio.use_cases, snap(), clade, sense)

    @app.get("/api/studio/{clade}/{sense}/run/options", response_model=models.RunOptionsOut)
    def run_options(clade: str, sense: str) -> Any:
        return guarded(runs.options, snap(), clade, sense)

    @app.post("/api/studio/{clade}/{sense}/run", status_code=201, response_model=models.JobOut)
    def run(clade: str, sense: str, body: RunBody) -> Any:
        try:
            return jobs.start(snap(), clade, sense, body.model_dump())
        except studio.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except runs.RunError as e:
            raise HTTPException(409 if "already" in str(e) else 422, str(e)) from e

    def job_or_404(job_id: str) -> dict[str, Any]:
        try:
            return jobs.get(job_id)
        except KeyError as e:
            raise HTTPException(404, f"no run {job_id!r}") from e

    @app.get("/api/studio/jobs", response_model=list[models.JobOut])
    def job_list(clade: str | None = None, sense: str | None = None, limit: int = 20) -> Any:
        return jobs.recent(min(max(limit, 1), 200), clade, sense)

    @app.get("/api/studio/jobs/{job_id}", response_model=models.JobOut)
    def job(job_id: str) -> Any:
        return job_or_404(job_id)

    @app.post("/api/studio/jobs/{job_id}/cancel", response_model=models.JobOut)
    def cancel(job_id: str) -> Any:
        job_or_404(job_id)
        return jobs.cancel(job_id)

    @app.get("/api/studio/jobs/{job_id}/events", response_class=StreamingResponse)
    def events(job_id: str) -> StreamingResponse:
        """The live events contract (bench ``--events``) as Server-Sent Events."""
        job_or_404(job_id)
        return StreamingResponse(
            runs.tail_events(
                jobs.dir(job_id) / "events.jsonl",
                lambda: jobs.get(job_id)["status"] not in runs.ACTIVE,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/studio/jobs/{job_id}/report", response_class=PlainTextResponse)
    def report(job_id: str) -> str:
        j = job_or_404(job_id)
        p = Path(j.get("report_md") or jobs.dir(job_id) / "report" / "replay_report.md")
        if not p.is_file():
            raise HTTPException(404, "no report for this run")
        return p.read_text(encoding="utf-8")

    @app.get("/api/studio/jobs/{job_id}/files/{path:path}")
    def job_file(job_id: str, path: str) -> FileResponse:
        """An image a run wrote into its folder (frames for the live view)."""
        job_or_404(job_id)
        root = jobs.dir(job_id).resolve()
        p = (root / path).resolve()
        if root not in p.parents or p.suffix.lower() not in IMAGE_TYPES or not p.is_file():
            raise HTTPException(404, "no such file")
        return FileResponse(p, media_type=IMAGE_TYPES[p.suffix.lower()])

    ex = explore.Explore(cfg, lambda: studio.species(snap()), kw.get("explore_transport"))

    async def outside(coro: Any) -> Any:
        try:
            return await coro
        except explore.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except explore.BadQuery as e:
            raise HTTPException(422, str(e)) from e
        except explore.ExploreError as e:
            raise HTTPException(502, str(e)) from e

    @app.get("/api/studio/explore/species", response_model=models.ExploreSpeciesOut)
    async def explore_species(q: str) -> Any:
        """Taxa matching a common or scientific name, whether or not the library has them."""
        return await outside(ex.species(q))

    @app.get("/api/studio/explore/taxon/{key}", response_model=models.ExploreTaxonOut)
    async def explore_taxon(key: int) -> Any:
        """The taxon's senses, ranked by how many papers cover each."""
        return await outside(ex.taxon(key))

    @app.get("/api/studio/explore/taxon/{key}/papers", response_model=models.ExplorePapersOut)
    async def explore_search(key: int, q: str, sort: str = "cited", page: int = 1) -> Any:
        """Papers on any sense or trait (q: terms separated by commas, any one of which)."""
        return await outside(ex.search_papers(key, q, sort, page))

    @app.get(
        "/api/studio/explore/taxon/{key}/{sense}/papers", response_model=models.ExplorePapersOut
    )
    async def explore_papers(key: int, sense: str, sort: str = "cited", page: int = 1) -> Any:
        """Papers on one sense of the taxon (sort: cited | recent), 25 a page."""
        return await outside(ex.papers(key, sense, sort, page))

    add_research_routes(app, cfg, kw.get("research_transport"))

    # ------------------------------------------------------------------ web app

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/studio")

    def index() -> Response:
        page = STATIC / "index.html"
        if not page.is_file():
            return HTMLResponse(
                "<p>The web app is not built. Run <code>make build</code>.</p>", status_code=503
            )
        return FileResponse(page, headers={"Cache-Control": "no-cache"})

    @app.get("/studio", include_in_schema=False)
    def studio_home() -> Response:
        return index()

    @app.get("/studio/{rest:path}", include_in_schema=False)
    def studio_page(rest: str) -> Response:
        asset = (STATIC / rest).resolve()
        if rest.startswith("assets/") and STATIC.resolve() in asset.parents and asset.is_file():
            return FileResponse(asset, headers={"Cache-Control": "public, max-age=31536000"})
        return index()

    @app.get("/api/studio/{rest:path}", include_in_schema=False)
    def api_404(rest: str) -> Response:
        raise HTTPException(404, f"no API route /api/studio/{rest}")

    if cfg.password:
        return BasicAuth(app, cfg.password)
    return app


def app_factory() -> Any:
    """``uvicorn --factory senseai_studio.app:app_factory``."""
    return create_app()
