import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { UploadRequest } from "../api/types";
import { Badge, ErrorState } from "../components/AsyncState";

import { usePage } from "../api/usePage";
import { PageControls } from "../components/PageControls";

const maxBytes = 20_000_000;

export function validateImageFile(file: File): string | null {
  if (!["image/png", "image/jpeg"].includes(file.type)) {
    return "Only PNG and JPEG images are accepted.";
  }
  if (!file.size || file.size > maxBytes) {
    return "Image must be between 1 byte and 20 MB.";
  }
  return null;
}

export function Upload() {
  const [datasetId, setDatasetId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const datasets = usePage(api.datasets);
  const batches = usePage(useCallback((offset: number) => api.batches(datasetId, offset), [datasetId]), !!datasetId);
  const uploads = usePage(api.uploads);
  const [latest, setLatest] = useState<UploadRequest | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [fileError, setFileError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const selectFile = (next: File | null) => {
    if (!next) return;
    const invalid = validateImageFile(next);
    setFileError(invalid ?? "");
    setFile(invalid ? null : next);
  };

  const submit = () => {
    if (!file || (datasetId && !batchId) || submitting) return;
    setSubmitting(true);
    setError(null);
    api.upload(file, datasetId || undefined, batchId || undefined)
      .then((created) => {
        setLatest(created);
        uploads.first();
      })
      .catch(setError)
      .finally(() => setSubmitting(false));
  };

  return (
    <section>
      <header className="page-header"><div><span className="eyebrow">Controlled intake</span><h1>Image upload</h1><p>Uploads are validated, staged and persisted as requests. This M4 contract does not auto-register a catalog asset or run inference.</p></div></header>
      {error ? <ErrorState error={error} /> : null}
      <div className="two-column">
        <div className="panel">
          <label className="file-drop">Select PNG or JPEG<input type="file" accept="image/png,image/jpeg" onChange={(event) => selectFile(event.target.files?.[0] ?? null)} /></label>
          {fileError ? <p className="field-error" role="alert">{fileError}</p> : null}
          {preview ? <img className="upload-preview" src={preview} alt="Selected upload preview" /> : null}
          <label>Requested dataset<select value={datasetId} onChange={(event) => { setDatasetId(event.target.value); setBatchId(""); }}><option value="">No scope selected</option>{datasetId && !datasets.items.some(item => item.id === datasetId) && <option value={datasetId}>{datasetId}</option>}{datasets.items.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.dataset_name} v{dataset.version}</option>)}</select></label>
          <PageControls page={datasets} label="datasets" />
          <label>Requested batch<select value={batchId} disabled={!datasetId} onChange={(event) => setBatchId(event.target.value)}><option value="">No batch selected</option>{batchId && !batches.items.some(item => item.id === batchId) && <option value={batchId}>{batchId}</option>}{batches.items.map((batch) => <option key={batch.id} value={batch.id}>{batch.split ?? batch.kind} · {batch.member_count}</option>)}</select></label>
          {datasetId && <PageControls page={batches} label="batches" />}
          {datasetId && !batchId && <p>Select a batch to scope this request.</p>}
          <button disabled={!file || (!!datasetId && !batchId) || submitting} onClick={submit}>{submitting ? "Uploading…" : "Create upload request"}</button>
          {latest ? <div className="state-card"><strong>Request persisted</strong><span>{latest.id}</span><Badge value={latest.inference_state} /></div> : null}
        </div>
        <div className="panel">
          <h2>Upload requests</h2>
          <PageControls page={uploads} label="uploads" />
          {!uploads.loading && !uploads.error && !uploads.items.length && <p>No upload requests yet.</p>}
          <div className="request-list">
            {uploads.items.map((upload) => (
              <article key={upload.id}>
                <div><strong>{upload.original_filename}</strong><span>{upload.width}×{upload.height} · {(upload.byte_count / 1024).toFixed(1)} KiB</span></div>
                <Badge value={upload.status} /><Badge value={upload.inference_state} />
                <code>{upload.content_sha256}</code>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
