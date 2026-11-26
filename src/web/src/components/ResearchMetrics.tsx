import type { ResearchEvidence } from "../api/types";

// Preserve the registered nested result structure, including per-class rows,
// timing stages and hardware metadata; never substitute operational confidence.
function Values({ value, name }: { value: unknown; name?: string }) {
  if (value === null || value === undefined) return <>Unavailable</>;
  if (Array.isArray(value)) return <ol>{value.map((item, index) => <li key={index}><Values value={item} /></li>)}</ol>;
  if (typeof value === "object") return <dl>{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd><Values value={item} name={key} /></dd></div>)}</dl>;
  if (typeof value === "number" && name && ["precision", "recall", "f1", "macro_f1", "map50", "map50_95", "ap50", "ap50_95"].includes(name))
    return <>{(value * 100).toFixed(2)}% (fraction {value})</>;
  return <>{String(value)}</>;
}

export function ResearchMetrics({ evidence }: { evidence?: ResearchEvidence }) {
  return <section aria-label="Evaluation performance">
    <h3>Evaluation performance</h3>
    <p>{evidence?.scope ?? "Model-level research evidence"}</p>
    {!evidence?.available || !evidence.items.length ? <p>Authoritative evaluation and performance evidence unavailable for this snapshot.</p> : evidence.items.map(item => <article key={item.sha256}>
      <h4>{item.kind} · {item.evidence_class}</h4>
      <p>Manifest SHA-256: <code>{item.sha256}</code></p>
      {item.evaluation_sha256 && <p>Evaluation SHA-256: <code>{item.evaluation_sha256}</code></p>}
      <Values value={item.selection} />
      <Values value={item.results} />
      <ul>{item.limitations.map(value => <li key={value}>{value}</li>)}</ul>
    </article>)}
  </section>;
}
