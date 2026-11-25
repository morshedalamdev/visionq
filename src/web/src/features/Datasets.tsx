import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DatasetSummary } from "../api/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "../components/AsyncState";

import { usePage } from "../api/usePage";
import { PageControls } from "../components/PageControls";

export function Datasets() {
  const datasets = usePage(api.datasets);
  const [selection, setSelection] = useState("");
  const id = datasets.items.find(item => item.id === selection)?.id ?? datasets.items[0]?.id;
  const [selected, setSelected] = useState<DatasetSummary | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    let active = true;
    setSelected(null);
    setError(null);
    if (id) api.dataset(id).then(
      data => { if (active) setSelected(data); },
      reason => { if (active) setError(reason); },
    );
    return () => { active = false; };
  }, [id]);

  return (
    <section>
      <header className="page-header">
        <div>
          <span className="eyebrow">Catalog</span>
          <h1>Dataset quality</h1>
          <p>Persisted release identity, split membership and quality evidence.</p>
        </div>
      </header>
      <PageControls page={datasets} label="datasets" />
      {id && !error && selected?.dataset.id !== id && <LoadingState />}
      {error ? <ErrorState error={error} retry={datasets.retry} /> : null}
      {!datasets.loading && !datasets.error && !datasets.items.length ? (
        <EmptyState>No dataset versions are persisted yet.</EmptyState>
      ) : null}
      <div className="two-column">
        <div className="panel">
          <h2>Dataset versions</h2>
          <div className="select-list">
            {datasets.items.map((dataset) => (
              <button
                key={dataset.id}
                className={selected?.dataset.id === dataset.id ? "selected" : ""}
                onClick={() =>
                  setSelection(dataset.id)
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
        {selected && selected.dataset.id === id ? (
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
