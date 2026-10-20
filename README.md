# studio

SenseAI Studio: work on species sense models. Sources, model, real-time run, pipeline and use
cases, every item traced to a file. Studio is the source of truth for the front end.

```bash
make install && make serve      # http://127.0.0.1:8200/studio
make lint type test
```

Settings are environment variables, listed in [`.env.example`](.env.example).

## The Research tab (senseai-institute/research)

The research service is the backend and the source of truth for the evidence ledger, the
research assistant, impact previews, experiments and library proposals. Studio reaches it
through its own proxy, `/api/studio/research/*` → `RESEARCH_URL/api/research/*`, adding the
signed-in name (`X-SenseAI-User`) and the shared secret (`X-SenseAI-Proxy-Token`, from
`RESEARCH_PROXY_TOKEN`). Headers of those names sent by the browser are dropped.

- `web/src/research/client.ts`: a typed call for every research route. The contract is
  research's `docs/API.md`; the schemas are at `/api/studio/research/openapi.json`.
- `web/src/research/adapt.ts`: research payloads and chat events → what Studio renders. Its
  tests run against events recorded from the research service
  (`web/src/research/fixtures/research_events.json`); re-record them with research's
  `packages/senseai-research/scripts/record_events.py` when research changes a payload.
- `web/src/tabs/research.ts`: the tab. Chat on the left; on the right *To check* (this
  clade's least-verified values and open questions), *Claim*, *Impact*, *Experiment* and
  *Settings* (which API keys the research service has, with a *Test* button each).

To run both on Railway, follow research's `docs/DEPLOY.md`: set `RESEARCH_URL` and
`RESEARCH_PROXY_TOKEN` here, and the same token on the research service.
