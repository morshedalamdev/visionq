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

## 25 November 2026 acceptance handoff

Owner-reported Azure baseline is commit `23bda9d` on Linux AMD64,
Standard_E4as_v4, AMD EPYC 7452 with AVX2, 4 vCPUs and 32 GiB allocated.
Retain the three-file Compose command and existing private networks. The
deployed model overlay is `/opt/visionq/compose.models.yaml`. Capture its
redacted launch settings for comparison before adopting any tracked replacement.
The owner reported both models healthy, real inference, expected retrieval
ranking and four successful authenticated MCP calls.

| Identity | Generation | Embedding |
| --- | --- | --- |
| Alias | qwen3-4b-instruct-2507 | embeddinggemma-300m |
| Revision | cdbee75f17c01a7cc42f958dc650907174af0554 | 57c266a740f537b4dc058e1b0cda161fd15afa75 |
| SHA-256 of snapshot manifest | aef8c9c1b3f6d622ee79c580fd2a65596e74d95dbc20b5bd000de528967d8a50 | 4a35ef17c7c0af1a4e5f86b5fdb9ba775ef0b58e1b0e847384cc91e6f0735e09 |
| Runner, dtype | Generation, FP32 | Pooling, FP32 |
| Context, concurrent sequences | 2048, 1 | 2048, 1 |
| CPU threads, RAM cap, shared memory | 0,2 / 24 GiB / 2 GiB | 1,3 / 6 GiB / 1 GiB |
| CPU KV cache | 1 GiB | No explicit override in deployed configuration |

Both mounts are read-only and both runners use eager execution and offline
settings. Owner-reported image tag is `visionq-vllm:0.15.1-avx2`, vLLM source
`1892993bc18e243e2c05841314c5e9c06a80c70d`, PyTorch `2.10.0+cpu`, image
ID `sha256:50a08e0381da7779a29f919db21cb47d7c64cbdc35130be71937d2dad8791b2a`.
The Docker image ID identifies local image configuration. V01 still needs the
portable platform digests and owner confirmation of EmbeddingGemma account
acceptance. [Qwen model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
and [EmbeddingGemma access terms](https://huggingface.co/google/embeddinggemma-300m).

### Azure VM (Remote)

Deploy the reviewed source by fast-forwarding the existing checkout. The probe
runs inside the existing MCP container, using its installed dependencies and
bearer token. Leave the deployed application and model images running.

```bash
cd /opt/visionq/app
git fetch origin main
git merge --ff-only origin/main
git rev-parse HEAD

compose=(sudo docker compose -f compose.yaml -f /opt/visionq/compose.azure.yaml
  -f /opt/visionq/compose.models.yaml --profile tools)
umask 077
set -o pipefail
run_dir="artifacts/m1t3-live/benchmark-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run_dir"
git rev-parse HEAD > "$run_dir/probe-commit.txt"
lscpu > "$run_dir/cpu.txt"
mapfile -t models < <("${compose[@]}" ps -q vllm-gen vllm-embed)
[[ ${#models[@]} -eq 2 ]] || exit 1
sudo -v
state_format='{{.Name}} {{.Image}} {{.State.Running}} {{.State.OOMKilled}} {{.RestartCount}}'
sudo docker inspect --format "$state_format" "${models[@]}" > "$run_dir/before.txt"
start=$(date -u +%FT%TZ)
(
  while :; do
    printf '%s\n' "$(date -u +%FT%TZ)"
    sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' "${models[@]}"
    sleep 1
  done
) > "$run_dir/model-memory.txt" &
sampler=$!
trap 'kill "$sampler" 2>/dev/null || true' EXIT
"${compose[@]}" exec -T mcp /app/.venv/bin/python - < src/model_client/t3_probe.py \
  | tee "$run_dir/probe.jsonl"
probe_status=$?
end=$(date -u +%FT%TZ)
kill "$sampler" 2>/dev/null || true
wait "$sampler" 2>/dev/null || true
trap - EXIT
sudo docker inspect --format "$state_format" "${models[@]}" > "$run_dir/after.txt"
sudo docker events --since "$start" --until "$end" \
  --filter "container=${models[0]}" --filter "container=${models[1]}" \
  --filter event=oom --filter event=die --filter event=start > "$run_dir/model-events.txt"
printf 'start=%s end=%s probe_exit=%s\n' "$start" "$end" "$probe_status" \
  | tee "$run_dir/run-status.txt"
test "$probe_status" -eq 0
```

Require five successful rows and a median summary. For peak RAM, convert the
usage values to bytes, sum the two model values from each sample, and take the
maximum of those sums. Report it as a sampled peak and retain the timestamps.
Use the before/after states and event log to check for OOMs and restarts.
Reuse existing private-network evidence where the configuration is unchanged.
Record elapsed billable VM time and the applicable rate or observed credit use.

### Mac (Local)

After the Azure run and evidence capture, deallocate and verify control-plane
status using the authorized Azure account.

```bash
az vm deallocate -g rg-visionq-sea -n visionq-vm
az vm get-instance-view -g rg-visionq-sea -n visionq-vm \
  --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code" -o tsv
```

Expect `PowerState/deallocated`. For V04, Docker reported ARM64 and 7.75 GiB
of guest memory. The vLLM repository-name filter and standard Hugging Face
snapshot paths yielded no matches. The observed Azure FP32 footprint exceeds
the current guest capacity. A native ARM64 vLLM runtime with the same pinned
models and a lower-memory configuration needs an owner decision and an actual
dual-service restart on an internal-only network.
