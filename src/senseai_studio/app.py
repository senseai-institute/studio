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
    GET  /api/studio/{clade}/{sense}/design          circuit types, knobs, research candidates,
                                                     designs (the Design tab)
    POST /api/studio/{clade}/{sense}/designs         new design (from candidates) -> draft
    GET  /api/studio/designs/{id}                    one design
    PUT  /api/studio/designs/{id}                    edit (back to draft)
    POST /api/studio/designs/{id}/check              senseai-circuits design check -> validated
    POST /api/studio/designs/{id}/adopt              profile patch (circuits: block), tells research
    POST /api/studio/designs/{id}/reject             with a reason, tells research
    GET  /api/studio/designs/{id}/patch              the profile spec diff of an adopted design
    POST /api/studio/design/figures                  paper figures for knob values (live preview)
    GET  /api/studio/explore/species?q=              any taxon by name (GBIF)
    GET  /api/studio/explore/taxon/{key}             its senses, ranked by papers (OpenAlex)
    GET  /api/studio/explore/taxon/{key}/{sense}/papers  the papers on one sense
    *    /api/studio/research/*                      proxy to RESEARCH_URL (when set)

Every JSON response carries ``provenance``. Studio reads repos read-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel, Field

from senseai_studio import __version__, designs, explore, models, runs, studio
from senseai_studio.auth import BasicAuth, user_of
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


class DesignBody(BaseModel):
    """A new or edited design: the senseai-circuits design@1 fields a person sets."""

    title: str | None = Field(default=None, max_length=200)
    profile: str | None = Field(default=None, description="the profile spec the design is for")
    values: dict[str, Any] | None = Field(default=None, description="knob -> value (dotted names)")
    bindings: dict[str, dict[str, Any]] | None = Field(
        default=None, description="knob -> {candidate_id, claim_ids, note}"
    )
    candidate_ids: list[str] | None = Field(default=None, description="research candidates used")
    notes: str | None = Field(default=None, max_length=5000)


class ReasonBody(BaseModel):
    """A person's reason for adopting or rejecting a design."""

    rationale: str = Field(min_length=1, max_length=5000)


class FiguresBody(BaseModel):
    """Knob values to draw the paper figures for."""

    values: dict[str, Any] = Field(default_factory=dict)
    circuits: list[str] | None = None


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

    @app.get(
        "/api/studio/explore/taxon/{key}/{sense}/papers", response_model=models.ExplorePapersOut
    )
    async def explore_papers(key: int, sense: str, sort: str = "cited", page: int = 1) -> Any:
        """Papers on one sense of the taxon (sort: cited | recent), 25 a page."""
        return await outside(ex.papers(key, sense, sort, page))

    store = designs.Designs(cfg, designs.Research(cfg, kw.get("research_transport")))
    app.state.designs = store

    def design_op(fn: Any, *a: Any) -> Any:
        try:
            return fn(*a)
        except designs.DesignError as e:
            raise HTTPException(e.status, str(e)) from e
        except studio.NotFound as e:
            raise HTTPException(404, str(e)) from e

    def who(request: Request) -> str:
        return user_of(request.headers.get("authorization"))

    @app.get("/api/studio/{clade}/{sense}/design", response_model=models.DesignPageOut)
    def design_page(clade: str, sense: str, request: Request) -> Any:
        """Circuit types and knobs for this sense, research's candidates, and the designs."""
        return design_op(designs.page, snap(), store, clade, sense, who(request))

    @app.post(
        "/api/studio/{clade}/{sense}/designs", status_code=201, response_model=models.DesignOut
    )
    def design_new(clade: str, sense: str, body: DesignBody, request: Request) -> Any:
        """Start a design (draft); research hears which candidates it uses."""
        c, s = guarded(snap().sense, clade, sense)
        return design_op(store.create, c.key, s.id, body.model_dump(), who(request))

    @app.get("/api/studio/designs/{did}", response_model=models.DesignOut)
    def design_get(did: str) -> Any:
        return design_op(store.get, did)

    @app.put("/api/studio/designs/{did}", response_model=models.DesignOut)
    def design_edit(did: str, body: DesignBody, request: Request) -> Any:
        """Edit values, bindings, title or profile; the design goes back to draft."""
        return design_op(store.update, did, body.model_dump(), who(request))

    @app.post("/api/studio/designs/{did}/check", response_model=models.DesignOut)
    def design_check(did: str, request: Request) -> Any:
        """Validate the values and rerun every touched circuit's paper figure."""
        return design_op(store.check, did, who(request))

    @app.post("/api/studio/designs/{did}/adopt", response_model=models.DesignOut)
    def design_adopt(did: str, body: ReasonBody, request: Request) -> Any:
        """Adopt a validated design: the profile spec patch, and research is told."""
        return design_op(store.adopt, snap(), did, body.rationale, who(request))

    @app.post("/api/studio/designs/{did}/reject", response_model=models.DesignOut)
    def design_reject(did: str, body: ReasonBody, request: Request) -> Any:
        return design_op(store.reject, did, body.rationale, who(request))

    @app.get("/api/studio/designs/{did}/patch", response_class=PlainTextResponse)
    def design_patch(did: str) -> PlainTextResponse:
        """The adopted design's profile spec diff (open it as a profiles PR)."""
        text = design_op(store.patch_text, did)
        return PlainTextResponse(
            text, headers={"Content-Disposition": f'attachment; filename="{did}.patch"'}
        )

    @app.post("/api/studio/design/figures", response_model=models.FiguresOut)
    def design_figures(body: FiguresBody) -> Any:
        """The paper figures for these knob values (senseai-circuits figures)."""
        return design_op(store.figures, body.values, body.circuits)

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
