# M3.T1 real training — 26 November 2026

M3.T1 passed. M3 remains open; M3.T2 was not executed.
Owner authorized private local real training in this chat. Frozen dataset and pretrained weights matched their handoff pins. MPS probe passed.

60 epochs, batch16, imgsz320, AdamW lr0=.001, cosine, patience20, seed42, deterministic=True, workers0, cache=False, amp=False; full effective arguments and environment are sealed in run/training-manifest.json.
Apple M4 / 16 GiB / MPS. Actual duration 1369.426 seconds (22m49.426s). Peak process RSS 919584768 bytes; this excludes a complete accounting of unified GPU memory. Trainer-reported maximum memory 2.27 GB. No OOM or nonfinite learning-curve values. Two MPS operations warn of nondeterminism, so bitwise repeatability is not claimed.

Final train box/class/DFL losses 1.26019/1.08503/1.38145; validation 1.40109/1.16396/1.41017. Best CSV validation mAP50–95 .44332 at epoch59; final best-checkpoint revalidation rounded P/R/mAP50/mAP50–95 .746/.670/.762/.444. Revalidation and epoch metrics are distinct measurements. Crazing recall .131 and AP50–95 .127 are limitations; no corrective run recommended without a specific validated diagnosis. No test evaluation or test-based tuning.

Acceptance: preflight hashes/counts/device passed; 1287 train and258 validation staged, no test partition; all60 curve rows finite; both checkpoints reloaded with six correct classes; all3100 sealed artifacts and3596 export files verified; focused training tests19 passed. Logs: verify.log, tests.log, train-command.log. Learning curves: learning-curves.png and sealed results.csv. Original dataset unchanged.

Manifest SHA256: 0bbff140fb0697e431d76439087829f150207f0b540520968ee1f9954c120810

Checkpoint run/ultralytics/weights/best.pt: 34754401c0f2becaa5c3ed12ce9d1d2c082471f77dd0ad167bde26d0e9db23d0

Checkpoint run/ultralytics/weights/last.pt: 2851518b5ddad615f55ccb93e40961274ed9df52ee9a7a721f595e109dfe8ffe

## M3.T2 handoff (not executed)
Use this sealed run and frozen export-a. First run `uv run --locked --group train visionq eval-select --export artifacts/m2t3-release-v1-eNmh2g/export-a --export-sha a8c14d88958f29a3042ba8b925584a9d6c770f60979cedb8bf9817ed393dc3c6 --run artifacts/m3t1-real-20261126/run --run-sha 0bbff140fb0697e431d76439087829f150207f0b540520968ee1f9954c120810 --output artifacts/m3t2-real-selection --device mps --real-release-approved` to select settings using validation only. Verify its returned digest with `eval-verify --selection artifacts/m3t2-real-selection --selection-sha DIGEST`. Freeze that selection before the single `eval-test` on the252 held-out images, using the same export pins and selection digest, a new output directory and `--device mps --real-release-approved`. Then run eval-verify-test and the separately recorded performance benchmark/verification; report per-class metrics, confusion/error analysis and hardware latency. Do not tune after seeing held-out results. Inspect existing evaluation acceptance protocol before execution.
