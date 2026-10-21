# Upstream: what Studio reads, and at which commits

Studio never imports upstream code into its server and never writes to an upstream checkout. It
reads files, runs CLIs, and runs `src/senseai_studio/probe.py` in a subprocess with whichever
interpreter can import the upstream package. Below are the commits Studio was built and tested
against, and what each one contributes.

| repo | commit | what Studio uses |
|---|---|---|
| profiles | `018d2d6009959d0b66a90f234ffcb4da3c0a059d` (main, 2026-10-17) | `library/*.yaml` (read with line numbers), `library/CITATIONS.md`, `research/requests/*.yaml`, profile specs, and, through the probe, `Registry(strict=False)`, `research.consumers_by_path`, `rules.all_rules`, `Rule.distill` for scalar rules |
| world | `8ec2cfdfbfd1671a0b3aad0263f601018dc68edb` (main) | `src/senseai_world/prior/params.py`, loaded by file path (no torch): `PriorParams.from_library(<clade>.yaml).provenance()`; checkpoint metadata (`param_counts`, `model_id`, `provenance`) through the stack's Python |
| bench | `d7c963ac6497bf7b035cedbac47a3ee41913f975` (main) + [bench#5](https://github.com/senseai-institute/bench/pull/5) (`da66ce8`) | `replay-compare --events` (the live events contract), `--help` for feature detection, `SDK_PROFILES` / `SDK_WORLD_MODES` for the fixed arm names. #5 adds `--synthetic`, `profile:<name>@<world>` arms, `sample.ring` and `frame` events |
| sdk | `653589e4cd6fb2824fa0609ec603895c2fdfaec3` | only through bench (the `SenseAI` pipeline the SDK arms run). Studio does not change the SDK's API |
| ingest | `60e6381e1e580c16f8f50653e9baf041bad91c9d` | the DSEC folder layout `testing.make_dsec_fixture` writes, and `SyntheticReplay` (through the SDK's `synthetic` adapter) |
| tokens, reflex | `7b12b1e`, `9442c53` | only through the SDK |
| viewer | `8106abffd6c168386dca3dd2d5eef30796010d17` | design tokens (`web/src/theme.css`, copied), Basic auth and the SSE tail (ported into `auth.py` and `runs.tail_events`), the shape of the Run page's live view |
| research | `63b483cd61156d353248301542afaf8297634a6b`; Design tab: branch `claude/circuit-candidates` @ `b008f12` | `docs/SPEC.md` §8/§10: `/api/research/*` behind a proxy that adds `X-SenseAI-User`. Design tab: `GET /api/research/circuit-candidates[/{id}]`, `POST .../refresh` and `POST .../{id}/decision` (SPEC "Circuit candidates") |
| circuits | branch `claude/new-session-fhne7e` @ `bb975d2` (main is still empty) | `senseai-circuits knobs --json`: the knob registry (`name, unit, default, range, kind, source, doc`). Species values come from a spec's `circuits:` section or a prior bundle's `circuits` / `meta.circuits` (what `CircuitParams.from_bundle_meta` reads). `prior --library`, the token-space prior. Design tab: `catalogue --json`, `figures --values`, `design check -` and `design patch - --spec --name` (circuits docs/DESIGN.md, "From research to a prior"). Without the CLI: "circuits: not installed" |

## Assumed formats (until the upstream change lands)

These readers are written against the build prompt's description, not against a merged file.
Each one degrades to a "not present" badge, never to an error.

- **Evidence tables** (profiles P0, `library/tables/<clade>.<sense>.csv`): one row per library
  value. Columns are matched loosely:
  - path: `path` | `library_path` | `quantity` | `target`
  - status: `status` | `verification` | `verified`
  - quote: `quote` | `verbatim_quote` | `verbatim`

  A row counts as verified when its status is `verified`.
- **Rulebook** (profiles P0, `rulebook/*.yaml`): `rules: [{id, clade, sense, sets, species, status, reads: [library paths]}]`.
  A rule belongs to a sense when it names the clade and sense, or reads a path under them.
- **Pipeline steps** (profiles P0, `docs/pipeline/steps.yaml`): same format as
  `content/pipeline.yaml`. Studio prefers the profiles file when it exists.
- **Species file header**: Markdown or YAML front matter under `docs/pipeline/` naming the
  `clade` or `species`, with `job` and `proxy` (and optionally `started`).
- **Pre-registration and verdicts** (bench prereg, `bench/prereg/*.yaml`, `bench/runs/*/verdict.json`):
  records naming `clade` / `species` / `profile` (and optionally `sense`), with `id`, `hash`,
  `clips`, `frozen_at`, and `verdict`.
- **Certificates**: `profiles/registry/<species>/v*.json` with `certificate`.
- **Which circuits serve which sense**: `content/circuits.yaml` maps knob prefixes (`cs`, `emd`, `lgmd`, `x`, `ts`) to library modalities. It is founder-editable until circuits declares this itself.

## Not done here

- The viewer is unchanged: Studio is its own service on port 8200 with the same password.
  Mounting it under the viewer's URL (`/studio`, `/api/studio`) is a small viewer PR:
  - proxy both prefixes to `127.0.0.1:8200`;
  - add one nav link.
