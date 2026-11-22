import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../api/client", () => ({
  api: {
    datasets: vi.fn().mockResolvedValue({ items: [], page: {} }),
    dataset: vi.fn(),
    batches: vi.fn().mockResolvedValue({ items: [], page: {} }),
    runs: vi.fn().mockResolvedValue({ items: [], page: {} }),
    uploads: vi.fn().mockResolvedValue({ items: [], page: {} }),
    agentFixture: vi.fn().mockResolvedValue(null),
  },
}));

describe("VisionQ app", () => {
  it("renders navigation and the persistent dataset empty state", async () => {
    render(<App />);

    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dataset quality" })).toBeInTheDocument();
    expect(
      await screen.findByText("No dataset versions are persisted yet."),
    ).toBeInTheDocument();
  });
});
