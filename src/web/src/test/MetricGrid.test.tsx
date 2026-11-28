import { render, screen } from "@testing-library/react";
import { MetricGrid, displayMetric } from "../components/MetricGrid";
import type { Metric } from "../api/types";
import { describe, expect, it } from "vitest";

const base = {
  value_type: "number",
  denominator_name: "processed_image_count",
  denominator_value: 10,
  evidence_status: "available",
  reason: null,
} satisfies Partial<Metric>;

describe("metric evidence formatting", () => {
  it("keeps ratios as percentages and missing values unavailable", () => {
    expect(
      displayMetric({
        ...base,
        metric_name: "prediction_image_ratio",
        value: 0.25,
        unit: "fraction",
      } as Metric),
    ).toBe("25.0%");
    expect(
      displayMetric({
        ...base,
        metric_name: "prediction_image_ratio",
        value: null,
        unit: "fraction",
        evidence_status: "unavailable",
        reason: "no_successful_images",
      } as Metric),
    ).toBe("Unavailable");
  });

  it("renders denominators and evidence state", () => {
    render(
      <MetricGrid
        metrics={[
          {
            ...base,
            metric_name: "predicted_box_count",
            value: 4,
            unit: "boxes",
            value_type: "integer",
          } as Metric,
        ]}
      />,
    );

    expect(screen.getByText("Predicted boxes")).toBeInTheDocument();
    expect(screen.getByText("Processed: 10")).toBeInTheDocument();
  });
});
