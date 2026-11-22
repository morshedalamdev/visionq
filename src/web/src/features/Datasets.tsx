import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Dataset, DatasetSummary } from "../api/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "../components/AsyncState";

export function Datasets() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<DatasetSummary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    api.datasets()
      .then(async (response) => {
        setDatasets(response.items);
        if (response.items[0]) {
          setSelected(await api.dataset(response.items[0].id));
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <section>
      <header className="page-header">
        <div>
          <span className="eyebrow">Catalog</span>
          <h1>Dataset quality</h1>
          <p>Persisted release identity, split membership and quality evidence.</p>
        </div>
      </header>
      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} retry={load} /> : null}
      {!loading && !error && !datasets.length ? (
        <EmptyState>No dataset versions are persisted yet.</EmptyState>
      ) : null}
      <div className="two-column">
        <div className="panel">
          <h2>Dataset versions</h2>
          <div className="select-list">
            {datasets.map((dataset) => (
              <button
                key={dataset.id}
                className={selected?.dataset.id === dataset.id ? "selected" : ""}
                onClick={() =>
                  api.dataset(dataset.id).then(setSelected).catch(setError)
                }
              >
                <span>
                  <strong>{dataset.dataset_name} v{dataset.version}</strong>
                  <small>{dataset.asset_count} assets · {dataset.batch_count} batches</small>
                </span>
                <Badge value={dataset.evidence_kind} />
              </button>
            ))}
          </div>
        </div>
        {selected ? (
          <div className="panel">
            <div className="panel-heading">
              <div>
                <h2>{selected.dataset.dataset_name} v{selected.dataset.version}</h2>
                <code>{selected.dataset.release_manifest_sha256}</code>
              </div>
              <Badge value={selected.dataset.evidence_kind} />
            </div>
            <div className="stats-row">
              <div><strong>{selected.dataset.asset_count}</strong><span>Assets</span></div>
              <div><strong>{selected.dataset.error_quality_issue_count}</strong><span>Errors</span></div>
              <div><strong>{selected.dataset.warning_quality_issue_count}</strong><span>Warnings</span></div>
            </div>
            <h3>Frozen splits</h3>
            <div className="bar-list">
              {Object.entries(selected.splits).map(([split, count]) => (
                <div key={split}><span>{split}</span><strong>{count}</strong></div>
              ))}
              {!Object.keys(selected.splits).length ? <p>Split membership unavailable.</p> : null}
            </div>
            <h3>Quality by rule</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Rule</th><th>Severity</th><th>Findings</th><th>Assets</th></tr></thead>
                <tbody>
                  {selected.quality_by_rule.map((row) => (
                    <tr key={`${row.rule_id}-${row.severity}`}>
                      <td>{row.rule_id}</td><td>{row.severity}</td>
                      <td>{row.count}</td><td>{row.asset_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
