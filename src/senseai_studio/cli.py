# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""``senseai-studio serve | check | openapi``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from senseai_studio.settings import Settings


def cmd_serve(a: argparse.Namespace) -> int:
    """Run the server (uvicorn)."""
    import uvicorn

    from senseai_studio.app import create_app

    cfg = Settings.from_env()
    uvicorn.run(create_app(cfg), host=a.host, port=a.port or cfg.port, log_level="info")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    """Print what is missing per clade+sense; optionally write use-case templates."""
    from senseai_studio import studio
    from senseai_studio.facts import content

    cfg = Settings.from_env()
    snap = studio.Snapshot.take(cfg)
    if not snap.clades:
        print(
            f"error: no library under {cfg.profiles / 'library'} (set SENSEAI_PROFILES_REPO)",
            file=sys.stderr,
        )
        return 2
    rows = studio.check(snap)
    if a.write_templates:
        made = content.write_templates(cfg.content, [(r["niche"], r["sense"]) for r in rows])
        for p in made:
            print(f"wrote {p}")
        rows = studio.check(studio.Snapshot.take(cfg))
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    h = studio.health(snap)
    print(
        f"profiles {cfg.profiles} @ {(h['repos']['profiles']['sha'] or 'no git')[:12]} · "
        f"engine {h['engine']}" + (f" ({h['engine_error']})" if h["engine_error"] else "")
    )
    for r in rows:
        print(f"\n{r['clade']}/{r['sense']}  {r['state']}  step {r['step']}/{r['steps']}")
        for m in r["missing"]:
            print(f"  - {m}")
    return 0


def cmd_openapi(_a: argparse.Namespace) -> int:
    """Print the OpenAPI document."""
    from senseai_studio.app import create_app

    app = create_app(Settings.from_env())
    print(json.dumps(getattr(app, "app", app).openapi(), indent=1))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(prog="senseai-studio", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the Studio server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=None, help="default STUDIO_PORT or 8200")
    s.set_defaults(fn=cmd_serve)
    c = sub.add_parser("check", help="list what is missing per species and sense")
    c.add_argument("--json", action="store_true")
    c.add_argument(
        "--write-templates",
        action="store_true",
        help="create a use-case template for every clade+sense without one",
    )
    c.set_defaults(fn=cmd_check)
    o = sub.add_parser("openapi", help="print the OpenAPI document")
    o.set_defaults(fn=cmd_openapi)
    a = ap.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
