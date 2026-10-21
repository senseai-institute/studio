# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Stand-in for ``senseai-circuits knobs --json`` and ``prior --library X --json`` (314732b)."""

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


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["knobs", "--json"]:
        print(json.dumps(KNOBS))
    elif args[:2] == ["prior", "--library"] and len(args) >= 3:
        print(json.dumps(prior(args[2])))
    else:
        sys.exit(2)
