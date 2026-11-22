# M4 code-complete / Azure readiness check — 22 November 2026

Starting commit: `d2b99a7282264aaa9d25ff46ec9408a9319a6ec7`.
No Azure resource, model service, cloud account, or paid feature was changed.

## Verdict

M4 is locally code-complete for synthetic-development contracts, but it is
**not ready for public or live-model deployment acceptance**. The application
image and private PostgreSQL/API/MCP path work. Production React authentication,
tracked CI repair, real model snapshots/services, real M2/M3 evidence and live
M4 integration remain required.

## Verified

### Application image

M4.T4-B01 was a transient registry/network failure, not a Dockerfile or
dependency fault. After the `python:3.11-slim-bookworm` and
`ghcr.io/astral-sh/uv:0.13.8` bases became available:

- ARM64 image: `6962daa22de00fbed44c7a66529c4785030772003d15379f9e44ed4ede70e4e8`
- Azure-target AMD64 image:
  `45920b1f3487833e4ed49636737b70f8f44674d7cc5da677b99ede531ed580f5`
- both images run `visionq info`;
- FastAPI imports successfully and MCP modules/imports pass in the AMD64 image;
- package versions: `mcp==2.3.0`, `fastapi==0.165.0`, `pillow==13.0.0`.

Evidence:
`artifacts/m4-readiness-20261122/docker-build.log`.

For reproducible VM images, pin both base references by the observed
multi-platform digests before freezing the Azure release:

- `python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`
- `ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85`

### Private Compose path

A fresh `pgvector` database was migrated through `0007_upload_requests`; the
read-only `visionq_mcp` role was applied; API, PostgreSQL and MCP started
successfully on the private Docker network:

- FastAPI `/app/datasets?limit=1`: HTTP 200 with bounded page metadata;
- authenticated MCP discovery returned exactly the five approved tools;
- DB, API and MCP remained private to the internal network; no MCP/DB port was
  published.

Evidence:
`artifacts/m4-readiness-20261122/compose-smoke.log`.

The React production service is not yet part of Compose. Vite is a local build
tool, not an Azure static frontend server. Before VM deployment choose and
approve one small serving boundary: same-origin static files through FastAPI,
or an internal Nginx/static service. Neither is configured today.

## React authentication boundary

`VITE_API_TOKEN` is compiled into browser JavaScript. A canary value was found
in the generated bundle, proving that it is not a secret. Any user with the
bundle can replay the current static API bearer token until it is rotated.
The API has no user identity, token audience, expiry, issuer, tenant or role
checks.

For the approved private/SSH-tunnel research deployment, keep the port bound to
loopback and do not place the token in a public build. The current token is
acceptable only as a local single-operator development credential.

For any continuously accessible or public frontend, the smallest secure
production boundary requiring approval is:

1. Register separate Microsoft Entra ID SPA and FastAPI API app registrations.
2. React uses authorization-code flow with PKCE through MSAL; the client ID and
   redirect URI are public configuration, not secrets.
3. The short-lived access token is held in memory and sent to the VisionQ API.
4. FastAPI validates signature, issuer, audience, expiry, tenant and delegated
   `scp` or app `roles` claims before any route.
5. Keep `VITE_API_TOKEN` only as an explicit local-development switch; never
   emit it in a production bundle.

The React SPA/PKCE pattern is described in Microsoft's
[React SPA preparation guidance](https://learn.microsoft.com/en-us/entra/identity-platform/tutorial-single-page-app-react-prepare-app)
and the [access-token-to-API flow](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-spa-acquire-token).
The API must independently validate the token's signature, issuer, audience and
expiry rather than merely checking that a bearer header exists.

This is a material authentication/topology decision. It is **not implemented**
and must not be silently substituted for the current private VM profile.

Evidence:
`artifacts/m4-readiness-20261122/vite-token-audit.log`.

## Service configuration gaps

Do not provision until the following operational inputs exist:

- `compose.t3.yaml` or equivalent definitions for separate generation and
  embedding vLLM services; none is tracked now;
- exact Qwen and EmbeddingGemma model access/manifests; only one local
  EmbeddingGemma `config.json` check and no complete snapshots are recorded;
- explicit live `VISIONQ_MCP_EMBEDDING_BACKEND=openai-compatible`, matching
  model/revision/dimension/prefix values, and a real ready retrieval index;
- API/MCP health endpoints plus Compose `healthcheck` and restart policy;
- strict required-variable checks for `VISIONQ_MCP_DATABASE_URL` and MCP token;
  current Compose allows empty values until process startup fails;
- an approved React static-serving service and production auth boundary;
- a current VM, quota, availability, CPU/dtype and price preflight.

The internal service topology itself is coherent: PostgreSQL is isolated, MCP is
isolated and bearer-protected, API is loopback-published, artifact storage is
mounted only into API/worker, and the MCP database role is read-only. The API
still uses the project DB owner role because it creates snapshots/uploads;
review a narrower `visionq_app` role before a public-facing deployment.

## M1.T3 prerequisites

Model identities:

- Generator: `Qwen/Qwen3-4B-Instruct-2507`, planned revision
  `cdbee75f17c01a7cc42f958dc650907174af0554`;
- Embedder: `google/embeddinggemma-300m`, planned revision
  `57c266a740f537b4dc058e1b0cda161fd15afa75`;
- full snapshots, exact file SHA-256 manifests, tokenizer/template/pooling
  configuration and authorized notices are still required;
- EmbeddingGemma remains license-gated; public accessibility does not establish
  that the owner accepted its terms.

Hardware and platform:

- candidate `Standard_E4_v4`: 4 x64 vCPUs, 32 GiB RAM, eastasia;
- 17 November preflight recorded 6 regional vCPUs and matching family quota,
  but both must be refreshed at allocation;
- Qwen weights alone are approximately 8 GiB at two bytes per parameter.
  EmbeddingGemma adds about 0.6 GiB in BF16, before process/KV-cache, database,
  API and host overhead. Thirty-two GiB is a candidate, not a passing memory
  result;
- vLLM CPU requires actual x86 FP32/BF16 and CPU instruction checks. Inspect
  `AVX512`/`AVX512_BF16` inside the VM before selecting dtype/image settings.
- bound model context, CPU KV cache and concurrency; measure both resident
  services, then five 120-second end-to-end questions and local offline restart.

Cost:

- recorded estimate: `$0.334/hour`;
- 55-dollar compute ceiling corresponds to about 164.7 VM hours, but the
  remaining credit and actual regional price must be rechecked;
- disk estimate was `$9.60/month` for 128 GiB Standard SSD LRS, plus any IP,
  egress and storage transactions;
- deallocation, not guest shutdown alone, must be verified.

## Open acceptance gates

- M2.T3: genuine disposition of all candidates, grouping review, real split
  release/freeze and DQ checks;
- M2.T4: real released-data ingest/reconcile/backup/restore and rights-reviewed
  Blob operation;
- M3: real released-data training, corrective-run decision, one held-out
  evaluation/performance run and persisted prediction backup/restore;
- hosted CI: latest M4 commits fail. `compose.t4.yaml` is absent while the
  workflow references it, and ignored `artifacts/m2t3-development/synthetic-only`
  data is absent from GitHub checkout. Add a React job after fixing these;
- production corpus approval and live EmbeddingGemma relevance/768-dimensional
  checks;
- M1.T3: actual model access, VM services, embedding/retrieval/MCP, five timed
  questions, isolation/deallocation and local offline restart;
- live M4: real retrieval, MCP client calls, UI history/evidence and model
  integration;
- M4 module regression gate, M5 agent/research, M6 offline recovery/report.

## Critical path to 30 November

Eight calendar days remain at this check. The remaining estimated M1/M2/M3/M5/M6
work cannot credibly be completed in sequence by one owner before 30 November if
all original gates are retained.

| Date | Critical path |
|---|---|
| 22–23 Nov | Resolve CI drift; make PM decision on private-only auth versus Entra production; finish M2.T3 release/freeze |
| 24 Nov | Real M3 training/selection/evaluation/persistence; preserve a negative or low score honestly |
| 25 Nov | M1 Stage 2 model access/terms/manifests; complete vLLM CPU overlays/probes |
| 26–27 Nov | Only after explicit PM/credit authorization, provision/recheck VM and run M1.T3 four gates plus offline local smoke |
| 28 Nov | Live retrieval, MCP and UI integration; close M4 module gate |
| 29–30 Nov | M5 minimum viable agent/research and M6/report; this slot is already insufficient relative to the 36–44 hour M5 estimate |

Required Project Manager decisions:

1. private SSH-tunnel-only first deployment, or approve Entra/public topology;
2. authorize the later Azure spend/quota refresh after model access succeeds;
3. prioritize report submission by 30 November or request a deadline extension;
4. approve any reduced research condition only with a documented scope decision.

No reduced scope, model substitution, cloud provisioning, or synthetic pass is
inferred by this report.
