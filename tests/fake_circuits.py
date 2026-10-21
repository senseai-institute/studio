# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Stand-in for ``senseai-circuits`` (circuits bb975d2): ``knobs --json``, ``prior --library X``,
``catalogue --json``, ``figures --values JSON``, ``design check -`` and ``design patch -``.

The shapes are the real CLI's; the numbers are not. A figure fails when ``lgmd.w_inhib`` is
above 3 (so tests can see a design that does not validate).
"""

import json
import sys

KNOBS = [
    {
        "name": "cs.sigma_center_deg",
        "unit": "deg",
        "default": 0.5,
        "range": [0.05, 10.0],
        "kind": "measured",
        "source": "cat retinal ganglion cells (Rodieck 1965)",
        "doc": "Standard deviation of the centre Gaussian.",
        "type": "float",
    },
    {
        "name": "emd.delay_tau_ms",
        "unit": "ms",
        "default": 35.0,
        "range": [1.0, 1000.0],
        "kind": "measured",
        "source": "Diptera (Borst & Egelhaaf 1989)",
        "doc": "Time constant of the delay filter.",
        "type": "float",
    },
    {
        "name": "lgmd.w_inhib",
        "unit": "ratio",
        "default": 0.5,
        "range": [0.0, 4.0],
        "kind": "proposed",
        "source": "Rind & Bramwell 1994; no fitted value",
        "doc": "S = relu(E - w_inhib * I).",
        "type": "float",
    },
    {
        "name": "ts.match_gate",
        "unit": "sigma^2",
        "default": 9.0,
        "range": [0.1, 1000.0],
        "kind": "physics",
        "source": "3-sigma gate",
        "doc": "Match cost above which tokens differ.",
        "type": "float",
    },
]


def prior(library: str) -> dict[str, object]:
    """The shape of ``senseai-circuits prior``: PriorParams.from_library(...).provenance()."""
    import yaml

    with open(library, encoding="utf-8") as fh:
        entry = yaml.safe_load(fh) or {}
    sigma = {
        "value": 5.0,
        "kind": "measured",
        "source": "felidae.senses.hearing.spatial_resolution (Heffner & Heffner 1988)",
    }
    for sense in entry.get("senses", []):
        sr = sense.get("spatial_resolution") if sense.get("id") == "hearing" else None
        if sr and sr.get("unit") == "deg":
            sigma = {
                "value": float(sr["value"]),
                "kind": "measured",
                "source": f"{entry.get('clade', '?')}.senses.hearing.spatial_resolution ()",
            }
    return {
        "ok": True,
        "source": "senseai_circuits.tokenspace.PriorParams",
        "params": {
            "sigma_bearing_deg": sigma,
            "w_loom": {
                "value": 0.5,
                "kind": "proposed",
                "source": "looming-escape literature; no felid value in library",
            },
            "match_gate": {"value": 9.0, "kind": "physics", "source": "3-sigma gate"},
        },
        "proposed": ["w_loom"],
    }


BY_NAME = {k["name"]: k for k in KNOBS}


def _fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(2)


def _check_values(values: dict) -> dict:
    for k, v in values.items():
        if k not in BY_NAME:
            _fail(f"unknown knob {k!r}")
        lo, hi = BY_NAME[k]["range"]
        if not lo <= v <= hi:
            _fail(f"{k}: {v} is outside [{lo}, {hi}]")
    return values


def figure(circuit: str, values: dict) -> dict:
    w = values.get("lgmd.w_inhib", 0.5)
    ok = w <= 3
    return {
        "circuit": circuit,
        "figure": True,
        "title": f"{circuit} figure",
        "paper": "fake",
        "x": {"label": "x", "unit": "deg"},
        "y": {"label": "y", "unit": ""},
        "series": [{"name": "circuit", "style": "measured", "points": [[0, 0], [1, 1.0 - w / 4]]}],
        "marks": {},
        "checks": [{"name": "fake check", "ok": ok, "detail": "w_inhib <= 3"}],
        "ok": ok,
        "ms": 1.0,
    }


def catalogue() -> dict:
    return {
        "circuits_version": "0.1.0-fake",
        "circuits": [
            {
                "prefix": "cs",
                "name": "Centre-surround",
                "modalities": ["vision"],
                "figure": True,
                "knobs": ["cs.sigma_center_deg"],
                "computes": "DoG",
                "papers": "Rodieck 1965",
                "keywords": [],
                "conserved": "vertebrate retina",
            },
            {
                "prefix": "ts",
                "name": "Token-space prior",
                "modalities": ["vision", "hearing"],
                "figure": False,
                "knobs": ["ts.match_gate"],
                "computes": "matching",
                "papers": "",
                "keywords": [],
                "conserved": "",
            },
        ],
        "measures": [
            {
                "knob": "ts.sigma_bearing_deg",
                "field": "spatial_resolution",
                "modalities": ["hearing"],
                "unit": "deg",
                "knob_unit": "deg",
                "mapping": "exact",
                "formula": "same",
            },
        ],
    }


def design(args: list[str]) -> None:
    d = json.load(sys.stdin)
    values = _check_values(d.get("values") or {})
    if args[0] == "check":
        figs = (
            []
            if "--no-figures" in args
            else [figure(c, values) for c in sorted({k.split(".")[0] for k in values})]
        )
        ok = bool(values) and all(f["ok"] for f in figs)
        print(
            json.dumps(
                {
                    "design_id": d["id"],
                    "ok": ok,
                    "status": "validated" if ok and figs else "draft",
                    "params": values,
                    "changed": [{"knob": k, "value": v} for k, v in values.items()],
                    "circuits": sorted({k.split(".")[0] for k in values}),
                    "figures": figs,
                    "checks": [],
                }
            )
        )
        return
    spec = args[args.index("--spec") + 1]
    name = args[args.index("--name") + 1] if "--name" in args else spec.rsplit("/", 1)[-1]
    with open(spec, encoding="utf-8") as fh:
        text = fh.read()
    block = "circuits:\n" + "".join(f"  {k}: {v}\n" for k, v in values.items())
    diff = f"--- a/{name}\n+++ b/{name}\n" + "".join(f"+{line}\n" for line in block.splitlines())
    print(
        json.dumps(
            {
                "ok": True,
                "design_id": d["id"],
                "text": text + block,
                "diff": diff,
                "circuits": values,
            }
        )
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["knobs", "--json"]:
        print(json.dumps(KNOBS))
    elif args[:2] == ["prior", "--library"] and len(args) >= 3:
        print(json.dumps(prior(args[2])))
    elif args[:1] == ["catalogue"]:
        print(json.dumps(catalogue()))
    elif args[:1] == ["figures"]:
        vals = _check_values(
            json.loads(args[args.index("--values") + 1]) if "--values" in args else {}
        )
        circuits = [args[i + 1] for i, a in enumerate(args) if a == "--circuit"] or ["cs"]
        figs = [figure(c, vals) for c in circuits]
        print(json.dumps({"ok": all(f["ok"] for f in figs), "figures": figs}))
    elif args[:1] == ["design"] and len(args) >= 3:
        design(args[1:])
    else:
        sys.exit(2)
