import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Batch, Dataset, UploadRequest } from "../api/types";
import { Badge, ErrorState } from "../components/AsyncState";

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
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [uploads, setUploads] = useState<UploadRequest[]>([]);
  const [latest, setLatest] = useState<UploadRequest | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [fileError, setFileError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reload = () => {
    api.uploads().then(({ items }) => setUploads(items)).catch(setError);
  };

  useEffect(() => {
    Promise.all([api.datasets(), api.batches(), api.uploads()])
      .then(([datasetPage, batchPage, uploadPage]) => {
        setDatasets(datasetPage.items);
        setBatches(batchPage.items);
        setUploads(uploadPage.items);
      })
      .catch(setError);
  }, []);

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
    if (!file) return;
    setSubmitting(true);
    setError(null);
    api.upload(file, datasetId || undefined, batchId || undefined)
      .then((created) => {
        setLatest(created);
        reload();
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
          <label>Requested dataset<select value={datasetId} onChange={(event) => { setDatasetId(event.target.value); setBatchId(""); }}><option value="">No scope selected</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.dataset_name} v{dataset.version}</option>)}</select></label>
          <label>Requested batch<select value={batchId} disabled={!datasetId} onChange={(event) => setBatchId(event.target.value)}><option value="">No batch selected</option>{batches.filter((batch) => batch.dataset_version_id === datasetId).map((batch) => <option key={batch.id} value={batch.id}>{batch.split ?? batch.kind} · {batch.member_count}</option>)}</select></label>
          <button disabled={!file || submitting} onClick={submit}>{submitting ? "Uploading…" : "Create upload request"}</button>
          {latest ? <div className="state-card"><strong>Request persisted</strong><span>{latest.id}</span><Badge value={latest.inference_state} /></div> : null}
        </div>
        <div className="panel">
          <h2>Upload requests</h2>
          <div className="request-list">
            {uploads.map((upload) => (
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
