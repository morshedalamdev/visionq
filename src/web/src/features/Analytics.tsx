import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Comparison,
  ContextSnapshot,
  Dataset,
  InferenceRun,
} from "../api/types";
import { Badge, ErrorState, LoadingState } from "../components/AsyncState";
import { MetricGrid } from "../components/MetricGrid";

const metricNames = [
  "batch_image_count",
  "processed_image_count",
  "failed_image_count",
  "pending_image_count",
  "running_image_count",
  "predicted_box_count",
  "images_with_prediction",
  "prediction_image_ratio",
  "boxes_per_processed_image",
  "processing_coverage",
  "quarantined_image_count",
  "quality_issue_count",
];

export function Analytics() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<InferenceRun[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [snapshot, setSnapshot] = useState<ContextSnapshot | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.datasets().then(({ items }) => {
      setDatasets(items);
      if (items[0]) setDatasetId(items[0].id);
    }).catch(setError);
  }, []);

  useEffect(() => {
    if (!datasetId) return;
    api.runs(datasetId).then(({ items }) => {
      setRuns(items);
      const first = items[0];
      if (first) {
        setBatchId(first.batch_id);
        setLeft(first.id);
        setRight(items[1]?.id ?? "");
      }
    }).catch(setError);
  }, [datasetId]);

  const capture = () => {
    const ids = right ? [left, right] : [left];
    if (!left || !batchId || !datasetId) return;
    setLoading(true);
    api.snapshot(datasetId, batchId, ids.filter(Boolean), metricNames)
      .then(async (created) => {
        setSnapshot(created);
        if (right) {
          const comparison = await api.compare(
            created.id,
            metricNames,
          );
          setComparisons(comparison.metrics);
        } else {
          setComparisons([]);
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };

  const scoped = snapshot?.payload.scope_set ?? [];

  return (
    <section>
      <header className="page-header"><div><span className="eyebrow">Canonical evidence</span><h1>Analytics</h1><p>Metrics come from an API-owned immutable snapshot. Missing values remain unavailable.</p></div></header>
      <div className="panel filters">
        <label>Dataset<select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>{datasets.map((item) => <option key={item.id} value={item.id}>{item.dataset_name} v{item.version}</option>)}</select></label>
        <label>Primary / left run<select value={left} onChange={(event) => { setLeft(event.target.value); setBatchId(runs.find((run) => run.id === event.target.value)?.batch_id ?? ""); }}>{runs.map((run) => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {run.status}</option>)}</select></label>
        <label>Optional right run<select value={right} onChange={(event) => setRight(event.target.value)}><option value="">No comparison</option>{runs.filter((run) => run.batch_id === batchId && run.id !== left).map((run) => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {run.status}</option>)}</select></label>
        <button onClick={capture}>Capture snapshot</button>
      </div>
      {loading ? <LoadingState label="Capturing repeatable-read evidence" /> : null}
      {error ? <ErrorState error={error} /> : null}
      {snapshot ? (
        <>
          <div className="evidence-banner"><Badge value="immutable snapshot" /><code>{snapshot.id}</code><span>SHA-256 {snapshot.payload_sha256}</span></div>
          {scoped.map((scope) => (
            <div className="panel" key={scope.role}>
              <div className="panel-heading"><h2>{scope.role}</h2><Badge value={String(scope.evidence.coverage.evidence_status)} /></div>
              <MetricGrid metrics={scope.evidence.metrics} />
            </div>
          ))}
          {comparisons.length ? (
            <div className="panel">
              <h2>Paired-run comparison</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Metric</th><th>Absolute</th><th>Relative</th><th>Percentage points</th></tr>
                  </thead>
                  <tbody>
                    {comparisons.map((comparison) => (
                      <tr key={comparison.metric_name}>
                        <td>{comparison.metric_name}</td>
                        <td>{comparison.absolute_delta ?? "Unavailable"}</td>
                        <td>{comparison.relative_delta === null ? comparison.relative_delta_reason : comparison.relative_delta.toFixed(3)}</td>
                        <td>{comparison.percentage_point_delta ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
          <div className="panel unavailable-panel">
            <h2>Evaluation performance</h2>
            <p>Precision, recall, mAP50 and mAP50–95 are unavailable because no authoritative persisted evaluation-record table exists in M4.T4. Synthetic training artifacts are not represented as live measurements.</p>
          </div>
        </>
      ) : null}
    </section>
  );
}
