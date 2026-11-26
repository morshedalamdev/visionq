import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ResearchMetrics } from "../components/ResearchMetrics";

afterEach(cleanup);
it("keeps historical missing evidence unavailable", () => {
  render(<ResearchMetrics />);
  expect(screen.getByText(/evidence unavailable/)).toBeVisible();
});
it("renders supplied metrics, class support, hardware and explicit fixture identity", () => {
  render(<ResearchMetrics evidence={{ available: true, scope: "model-level only", items: [{
    sha256: "fixture-manifest", kind: "evaluation", evidence_class: "synthetic-development",
    evaluation_sha256: null, selection: { threshold: 0.42 }, limitations: ["fixture only"],
    results: { precision: 0.123, per_class: [{ class_id: 2, support: 17 }], environment: { device: "cpu-test" } },
  }] }} />);
  for (const value of ["12.30% (fraction 0.123)", "17", "cpu-test", "fixture only", "evaluation · synthetic-development", "model-level only"])
    expect(screen.getByText(value)).toBeVisible();
});
