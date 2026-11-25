# M1.T3 and Azure deployment readiness checklist

This checklist prepares the deferred live-model gate. It does not authorize
provisioning, downloads, costs or model use. The Project Owner must approve
those actions in the M1.T3 chat.

## 1. Pre-provisioning authorization

- [ ] Owner approves the Azure quota/cost refresh and later VM creation.
- [ ] Azure for Students remaining balance and spending protection are rechecked.
- [ ] Microsoft.Compute remains registered.
- [ ] `eastasia` is rechecked for `Standard_E4_v4` availability, regional quota,
      family quota and physical capacity.
- [ ] Public compute, disk, IP, storage and egress prices are refreshed.
- [ ] Expected hours and storage remain within the approximately `$55` compute
      allocation and the remaining credit.
- [ ] SSH source IP, key ownership and deallocation procedure are agreed.

## 2. Model access and terms

- [ ] Qwen3-4B-Instruct-2507 access is verified at revision
      `cdbee75f17c01a7cc42f958dc650907174af0554`.
- [ ] Qwen Apache-2.0 notice/distribution obligations are recorded.
- [ ] EmbeddingGemma-300M terms are accepted by the owner/account.
- [ ] EmbeddingGemma access is verified at revision
      `57c266a740f537b4dc058e1b0cda161fd15afa75`.
- [ ] Complete snapshots are downloaded only after those checks.
- [ ] Per-file SHA-256 manifests cover weights, tokenizer, chat template,
      pooling config, model config and notices.
- [ ] Manifest hashes and snapshot revisions are frozen; model names alone are
      not accepted as identities.

## 3. Serving release configuration

- [ ] Track a `compose.t3.yaml` with separate `vllm-gen` and `vllm-embed`
      services.
- [ ] Pin vLLM image by platform-specific digest for Azure AMD64 and local ARM64.
- [ ] Configure explicit served-model aliases, `HF_HUB_OFFLINE=1`,
      `VLLM_NO_USAGE_STATS=1`, resource limits and timeout/cancel behavior.
- [ ] Qwen: verify `/v1/models`, `/v1/chat/completions`, schema-constrained JSON
      output, chat template and bounded context/output.
- [ ] EmbeddingGemma: verify `/v1/models`, `/v1/embeddings`, 768-dimensional
      finite nonzero vectors, query/document prefixes, 2,048-token limit,
      pooling and normalization.
- [ ] Keep vLLM internal; its API key alone is not treated as complete security
      because not every endpoint is protected. Expose no model port publicly.
- [ ] Set live MCP adapter fields:
      `VISIONQ_MCP_EMBEDDING_BACKEND=openai-compatible`,
      `VLLM_EMBEDDING_MODEL`,
      `VLLM_EMBEDDING_REVISION`,
      `VLLM_EMBEDDING_DIMENSIONS=768`,
      approved prefixes.

## 4. VM/platform checks

- [ ] Confirm AMD64 CPU flags, including `AVX512` and `AVX512_BF16`.
- [ ] Confirm vLLM CPU support for chosen BF16/FP32 dtype; EmbeddingGemma must
      not be silently run in unsupported FP16.
- [ ] Record VM image OS, architecture, CPU model, RAM, vLLM/package digests and
      Docker image digests.
- [ ] Start both model services resident at once.
- [ ] Record peak RAM, model load times and per-request latency.
- [ ] Keep question concurrency and CPU KV cache bounded.

## 5. Four original M1.T3 gates

- [ ] **V01 identity:** both actual services and aliases verified; exact files,
      revisions, image digests, dtype and launch configuration saved.
- [ ] **V02 retrieval/tool:** real vector of expected width, expected passage
      ranks first, schema-valid tool plan, one real MCP metric call and answer.
- [ ] **V03 VM feasibility:** five scoped questions, each below 120 seconds,
      no OOM, median latency, peak RAM, cost evidence, private access and
      deallocation.
- [ ] **V04 local fallback:** cached services restart with external egress
      blocked; real generation and embedding requests both pass.
- [ ] Run the M1 integration/regression gate before closing M1.

The M1.T3 fixture passage and metric question can run before the real M2 release or M3 detector evaluation.

## 6. Private app deployment

- [ ] Apply all migrations through `0007_upload_requests`.
- [ ] Apply and verify `visionq_mcp` read-only grants.
- [ ] Decide and implement a production frontend serving boundary
      (FastAPI static files or an internal static service).
- [ ] Keep the API/MCP/private model ports off the public internet.
- [ ] Keep `VITE_API_TOKEN` restricted to local development; never publish it.
- [ ] If any public UI is approved, first implement Entra SPA PKCE plus FastAPI
      JWT validation for signature, issuer, audience, expiry, tenant and
      scopes/roles.
- [ ] Verify API and MCP liveness at `/health`, database-backed application readiness at `/ready`, and recovery after restart. Exercise generation and retrieval separately.
- [ ] Restrict SSH to the current approved source IP; verify final
      `Stopped (deallocated)` state after use.

## 7. Pre-live M4 evidence

- [ ] Production document corpus approved and manifest frozen.
- [ ] Real 768-dimensional index rebuilt and integrity-verified.
- [ ] Real MCP client discovers/calls all five tools through Streamable HTTP.
- [ ] API/React reopen stored history, evidence and citations against the live
      snapshot/corpus.
- [ ] Only after these pass run the M4 module gate.

No unchecked item above is waived by a synthetic M4 result.
