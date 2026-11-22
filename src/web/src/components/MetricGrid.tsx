import type { Metric } from "../api/types";

export function displayMetric(metric: Metric): string {
  if (metric.value === null) return "Unavailable";
  if (metric.unit === "fraction") return `${(metric.value * 100).toFixed(1)}%`;
  if (metric.value_type && (metric.value_type === "integer")) return String(metric.value);
  return Number.isInteger(metric.value)
    ? String(metric.value)
    : metric.value.toFixed(3);
}

const labels: Record<string, string> = {
  batch_image_count: "Batch images",
  processed_image_count: "Processed",
  failed_image_count: "Failed",
  pending_image_count: "Pending",
  running_image_count: "Running",
  predicted_box_count: "Predicted boxes",
  images_with_prediction: "Images with predictions",
  prediction_image_ratio: "Prediction/image ratio",
  boxes_per_processed_image: "Boxes / processed image",
  processing_coverage: "Processing coverage",
  quarantined_image_count: "Quarantined images",
  quality_issue_count: "Quality findings",
};

export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="metric-grid">
      {metrics.map((metric) => (
        <article className="metric-card" key={metric.metric_name}>
          <small>{labels[metric.metric_name] ?? metric.metric_name}</small>
          <strong>{displayMetric(metric)}</strong>
          <span>
            {metric.denominator_name
              ? `${metric.denominator_name}: ${metric.denominator_value}`
              : metric.unit}
          </span>
          <em>{metric.evidence_status}</em>
          {metric.reason ? <p>{metric.reason}</p> : null}
        </article>
      ))}
    </div>
  );
}
