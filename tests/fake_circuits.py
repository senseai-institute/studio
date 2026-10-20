# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
"""Stand-in for ``senseai-circuits knobs --json`` (registry shape of circuits P1, dd913af)."""

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

if __name__ == "__main__":
    if sys.argv[1:] != ["knobs", "--json"]:
        sys.exit(2)
    print(json.dumps(KNOBS))
