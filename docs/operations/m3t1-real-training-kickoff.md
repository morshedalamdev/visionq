# M3.T1 real YOLO11n kickoff — prepared, not executed

Do not start training from this handoff yet. The development plan starts real M3
only after the M2 module gate. Real M2.T4 local ingestion/recovery now has evidence,
but mandatory rights-reviewed private Blob backup/restore is still blocked by
rights review and owner authorization. This document does not waive that gate.

## Exact inputs

- Working directory: `/Users/morshedalam/Developer/AI/visionq`.
- Release: `artifacts/m2t3-release-v1-eNmh2g/export-a`.
- Manifest: `a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6`.
- Frozen train/validation/test: 1287/258/252. Use training/validation only for
  development; the training adapter stages no test images.
- Local weights: `artifacts/model-weights/yolo11n.pt`, 5613764 bytes.
- Weights SHA-256: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
  Recomputed locally during T4; no download performed.
- Hardware observed: MacBook Air, Apple M4, 16 GB unified memory, 10 CPU cores.
  Prior synthetic MPS smoke passed; repeat the existing device preflight at
  actual training start rather than assuming the current ML environment is ready.
- Existing lock includes the `train` dependency group. Do not substitute an
  unpinned environment. T4 does not install that group or load model weights.

The earlier recorded weights/terms decision explicitly covered synthetic training
only. Obtain and record the owner's actual intended-use decision for real NEU-DET
training before passing `--rights-decision`; do not copy the old text as approval.
No public redistribution or Azure upload follows from private local training.

## Baseline and runtime planning

Reuse `worker.training`: 60 epochs maximum, batch16, imgsz320, AdamW, lr0=.001,
cosine schedule, patience20, seed42, deterministic=True, workers0, cache=False,
amp=False. Existing library augmentation is training-only and effective settings
are saved. Native-size RGB exports are letterboxed once by the loader.

A real runtime has not been measured. Reserve an overnight working window
(rough planning allowance 4–12 hours, not a benchmark or upper bound); M4 Air
thermal throttling and memory can materially change it. The previous synthetic
17-image/one-epoch run took 44.633 s including setup and cannot establish real
throughput. After the first three real epochs, estimate remaining time from
steady epoch durations times remaining epochs, plus final verification. Adjust
batch only for measured memory/device failure, document it, and use no test data.

## Commands for the future authorized training session

Run only after M2 gate clearance and explicit owner training authorization:

```zsh
cd /Users/morshedalam/Developer/AI/visionq
uv run --locked --group train visionq train-preflight \
  --export "$PWD/artifacts/m2t3-release-v1-eNmh2g/export-a" \
  --manifest-sha a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6 \
  --weights "$PWD/artifacts/model-weights/yolo11n.pt" \
  --weights-sha 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 \
  --device mps

: "${VISIONQ_REAL_TRAINING_RIGHTS_DECISION:?Set this to the actual owner-approved intended-use decision}"
training_parent=$(mktemp -d "$PWD/artifacts/m3t1-real-XXXXXX")
uv run --locked --group train visionq train-baseline \
  --export "$PWD/artifacts/m2t3-release-v1-eNmh2g/export-a" \
  --manifest-sha a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6 \
  --weights "$PWD/artifacts/model-weights/yolo11n.pt" \
  --weights-sha 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 \
  --output "$training_parent/run" --device mps --label baseline \
  --epochs 60 --batch 16 \
  --rights-decision "$VISIONQ_REAL_TRAINING_RIGHTS_DECISION" \
  > "$training_parent/train-command.log" 2>&1
training_exit=$?
printf '%s\n' "$training_exit" > "$training_parent/train-command.exit"
```

Stop and inspect if preflight/training fails; preserve partial output. Do not
interpret a directory's presence as completion. Do not start additional runs to
improve held-out results. The actual training manifest digest is available only
after success; use it with `train-verify --run PATH --manifest-sha DIGEST --load
--export RELEASE --export-sha DATASET_DIGEST` and save output/exit status.

## Acceptance

At least one valid trained model with verified checkpoints, full code/environment,
seed/configuration and rights provenance, training/validation learning curves,
actual duration/memory and complete training manifest. Preflight, leakage,
conversion and checkpoint reload checks must pass. Save effective loader/transform
settings and never stage test images during training. Low validation accuracy is
an observation, not permission to tune on test. Any one bounded corrective run
must be decided and finished before held-out evaluation in M3.T2. Freeze
checkpoint/settings before test; no invented accuracy target or feasibility claim.
