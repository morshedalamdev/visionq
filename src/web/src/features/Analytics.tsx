import { useCallback, useState } from "react";
import { api } from "../api/client";
import type {
  Comparison,
  ContextSnapshot,
  InferenceRun,
} from "../api/types";
import { Badge, ErrorState, LoadingState } from "../components/AsyncState";
import { MetricGrid } from "../components/MetricGrid";

import { usePage } from "../api/usePage";
import { PageControls } from "../components/PageControls";

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
  const datasets = usePage(api.datasets);
  const [choice, setChoice] = useState("");
  const datasetId = datasets.items.find(item => item.id === choice)?.id ?? datasets.items[0]?.id;
  return <section>
      <header className="page-header"><div><span className="eyebrow">Canonical evidence</span><h1>Analytics</h1><p>Metrics come from an API-owned immutable snapshot.</p></div></header>
      <label>Dataset<select value={datasetId ?? ""} onChange={event => setChoice(event.target.value)}>
        {datasets.items.map(item => <option key={item.id} value={item.id}>{item.dataset_name} v{item.version}</option>)}
      </select></label>
      <PageControls page={datasets} label="datasets" />
      {datasetId && <RunScopes key={datasetId} datasetId={datasetId} />}
    </section>;
}

function RunScopes({ datasetId }: { datasetId: string }) {
  const runs = usePage(useCallback((offset: number) =>
    api.runs(datasetId, undefined, undefined, offset), [datasetId]));
  const [choice, setChoice] = useState("");
  const primary = runs.items.find(run => run.id === choice) ?? runs.items[0];
  return <>
    <label>Primary / left run<select value={primary?.id ?? ""} onChange={event => setChoice(event.target.value)}>
      {runs.items.map(run => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {run.status}</option>)}
    </select></label>
    <PageControls page={runs} label="primary runs" />
    {primary && <ComparisonScope key={primary.id} datasetId={datasetId} left={primary} />}
  </>;
}

type Scope = { datasetId: string; left: InferenceRun };

function ComparisonScope(scope: Scope) {
  const { datasetId, left } = scope;
  const runs = usePage(useCallback((offset: number) =>
    api.runs(datasetId, undefined, undefined, offset), [datasetId]));
  const [right, setRight] = useState<InferenceRun>();
  return <>
    <label>Optional right run<select value={right?.id ?? ""} onChange={event => setRight(runs.items.find(item => item.id === event.target.value))}>
      <option value="">No comparison</option>
      {right && !runs.items.some(run => run.id === right.id) && <option value={right.id}>{right.id}</option>}
      {runs.items.filter(run => run.id !== left.id).map(run => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {run.status}</option>)}
    </select></label>
    <PageControls page={runs} label="comparison runs" />
    <Snapshot key={right?.id ?? "primary"} {...scope} right={right} />
  </>;
}

function Snapshot({ datasetId, left, right }: Scope & { right?: InferenceRun }) {
  const [snapshot, setSnapshot] = useState<ContextSnapshot | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const capture = () => {
    const scopes = right ? [left, right] : [left];
    setError(null);
    setComparisons([]);
    setSnapshot(null);
    setLoading(true);
    api.snapshot(datasetId, scopes, metricNames)
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
    <>
      <button onClick={capture} disabled={loading}>Capture snapshot</button>
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
    </>
  );
}
