import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Batch, Dataset, InferenceRun } from "../api/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "../components/AsyncState";

export function History({
  onInspect,
}: {
  onInspect: (runId: string) => void;
}) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [runs, setRuns] = useState<InferenceRun[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [status, setStatus] = useState("");
  const [modelId, setModelId] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.datasets().then(({ items }) => setDatasets(items)).catch(setError);
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.batches(datasetId || undefined),
      api.runs(datasetId || undefined, batchId || undefined, {
        status,
        modelId,
        createdAfter,
        createdBefore,
      }),
    ])
      .then(([batchPage, runPage]) => {
        setBatches(batchPage.items);
        setRuns(runPage.items);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [datasetId, batchId, status, modelId, createdAfter, createdBefore]);

  return (
    <section>
      <header className="page-header">
        <div><span className="eyebrow">Persistent records</span><h1>Run history</h1></div>
      </header>
      <div className="filters panel">
        <label>Dataset<select value={datasetId} onChange={(event) => { setDatasetId(event.target.value); setBatchId(""); }}><option value="">All datasets</option>{datasets.map((d) => <option key={d.id} value={d.id}>{d.dataset_name} v{d.version}</option>)}</select></label>
        <label>Batch<select value={batchId} onChange={(event) => setBatchId(event.target.value)}><option value="">All batches</option>{batches.map((b) => <option key={b.id} value={b.id}>{b.split ?? b.kind} · {b.member_count}</option>)}</select></label>
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All states</option>{["pending", "running", "succeeded", "partial", "failed"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Model<select value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="">All models</option>{Array.from(new Map(runs.map((run) => [run.model_id, run])).values()).map((run) => <option key={run.model_id} value={run.model_id}>{run.model_id.slice(0, 8)} · {run.architecture}</option>)}</select></label>
        <label>Created after<input type="date" value={createdAfter} onChange={(event) => setCreatedAfter(event.target.value)} /></label>
        <label>Created before<input type="date" value={createdBefore} onChange={(event) => setCreatedBefore(event.target.value)} /></label>
      </div>
      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} /> : null}
      {!loading && !error && !runs.length ? <EmptyState>No runs match these filters.</EmptyState> : null}
      <div className="run-list">
        {runs.map((run) => (
          <article key={run.id} className="panel run-card">
            <div className="run-card-main">
              <div><span className="eyebrow">{run.architecture}</span><h2>{run.id.slice(0, 8)}</h2><code>{run.model_sha256}</code></div>
              <Badge value={run.status} />
            </div>
            <div className="run-progress">
              <span style={{ width: `${(run.succeeded_items / Math.max(1, run.expected_items)) * 100}%` }} />
            </div>
            <div className="run-counts">
              <span>{run.succeeded_items} succeeded</span>
              <span>{run.pending_items} pending</span>
              <span>{run.failed_items} failed</span>
            </div>
            <div className="card-footer">
              <Badge value={run.evidence_kind} />
              <button onClick={() => onInspect(run.id)}>Reopen inspection</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
