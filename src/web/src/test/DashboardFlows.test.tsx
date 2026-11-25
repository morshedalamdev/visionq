import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { History } from "../features/History";
import { Upload } from "../features/Upload";
import { Inspection } from "../features/Inspection";
import { Analytics } from "../features/Analytics";

vi.hoisted(() => vi.stubEnv("VITE_API_TOKEN", "development-test-only"));

const json = (body: unknown, status = 200) => Response.json(body, { status });
const page = (items: unknown[], offset = 0, has_more = false) =>
  json({ items, page: { limit: 100, offset, has_more } });

function serve(handler: (url: URL, init: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((input: string, init: RequestInit) =>
    handler(new URL(input, "http://localhost"), init)));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const dataset = { id: "dataset-1", dataset_name: "Fixture", version: 1 };
const run = {
  id: "first-run", batch_id: "one", model_id: "model-1", architecture: "YOLO11n",
  status: "succeeded", evidence_kind: "synthetic", succeeded_items: 1, expected_items: 1,
};

it("resets history pagination on filter change and ignores the late old page", async () => {
  let finishOld!: (response: Response) => void;
  const inspect = vi.fn();
  serve(url => {
    if (!url.pathname.endsWith("/runs")) return page([]);
    if (url.searchParams.get("offset") === "100") return new Promise(resolve => { finishOld = resolve; });
    if (url.searchParams.get("status") === "partial") return page([{ ...run, id: "partial-run", status: "partial" }]);
    return page([run], 0, true);
  });
  render(<History onInspect={inspect} />);
  fireEvent.click(await screen.findByRole("button", { name: "Next runs" }));
  await waitFor(() => expect(finishOld).toBeDefined());
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "partial" } });
  expect(await screen.findByRole("heading", { name: "partial-" })).toBeVisible();
  await act(async () => finishOld(page([run], 100)));
  fireEvent.click(screen.getByRole("button", { name: "Reopen inspection" }));
  expect(inspect).toHaveBeenCalledWith("partial-run");
});

it("requires a complete scoped upload, reports an API rejection, then refreshes staged history", async () => {
  let posted = 0;
  const staged = { id: "staged", inference_state: "pending_registration", status: "ready",
    original_filename: "sample.png", width: 1, height: 1, byte_count: 12 };
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  serve((url, init) => {
    if (url.pathname.endsWith("/datasets")) return page([dataset]);
    if (url.pathname.endsWith("/batches")) {
      expect(url.searchParams.get("dataset_version_id")).toBe(dataset.id);
      return page([{ id: "batch-1", split: "validation", member_count: 1 }]);
    }
    if (init.method === "POST") {
      expect((init.body as FormData).get("dataset_version_id")).toBe(dataset.id);
      expect((init.body as FormData).get("batch_id")).toBe("batch-1");
      return ++posted === 1 ? json({ detail: "Scope conflict" }, 409) : json(staged);
    }
    return page(posted === 2 ? [staged] : []);
  });
  render(<Upload />);
  await screen.findByRole("option", { name: "Fixture v1" });
  fireEvent.change(screen.getByLabelText("Select PNG or JPEG"), { target: { files: [new File(["image"], "sample.png", { type: "image/png" })] } });
  fireEvent.change(screen.getByLabelText("Requested dataset"), { target: { value: dataset.id } });
  const submit = screen.getByRole("button", { name: "Create upload request" });
  expect(submit).toBeDisabled();
  await screen.findByRole("option", { name: /validation/ });
  fireEvent.change(screen.getByLabelText("Requested batch"), { target: { value: "batch-1" } });
  fireEvent.click(submit);
  expect(await screen.findByText("Scope conflict")).toBeVisible();
  fireEvent.click(submit);
  expect(await screen.findByText("Request persisted")).toBeVisible();
  expect(await screen.findByText("sample.png")).toBeVisible();
});

it("opens inspection directly, authenticates artifact fetches, and separates failed from zero detections", async () => {
  const image = { asset_id: "asset-one", status: "succeeded", detections: [],
    detection_count: 0, image_url: "/app/artifacts/one" };
  serve((url, init) => {
    if (url.pathname.endsWith("/images")) {
      return url.searchParams.get("offset") === "0" ? page([image], 0, true)
        : page([{ ...image, asset_id: "asset-two", status: "failed", last_error: "Fixture failure" }], 100);
    }
    if (url.pathname.includes("/artifacts/")) {
      expect(new Headers(init.headers).get("Authorization")).toBe("Bearer development-test-only");
      return json({ detail: "Artifact unavailable" }, 404);
    }
    return json({ ...run, dataset_name: "Fixture", dataset_release: 1 });
  });
  render(<Inspection initialRunId={run.id} />);
  expect(await screen.findByText("Successful zero-detection result.")).toBeVisible();
  expect(await screen.findByText("Artifact unavailable")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Next images" }));
  expect(await screen.findByText("failed. Fixture failure")).toBeVisible();
  expect(screen.queryByText("Successful zero-detection result.")).toBeNull();
});

it("preserves each batch in a paired comparison and clears evidence when the primary changes", async () => {
  const second = { ...run, id: "second-run", batch_id: "two" };
  serve((url, init) => {
    if (url.pathname.endsWith("/datasets")) return page([dataset]);
    if (url.pathname.endsWith("/runs")) return page(url.searchParams.has("batch_id") ? [run] : [run, second]);
    if (url.pathname.endsWith("/compare")) return json({ metrics: [] });
    const request = JSON.parse(String(init.body));
    expect(request.scopes).toEqual([
      { role: "left", dataset_version_id: dataset.id, batch_id: run.batch_id, inference_run_id: run.id },
      { role: "right", dataset_version_id: dataset.id, batch_id: second.batch_id, inference_run_id: second.id },
    ]);
    return json({ id: "snapshot-one", payload_sha256: "digest", payload: { scope_set: [] } });
  });
  render(<Analytics />);
  const right = await screen.findByLabelText("Optional right run");
  await waitFor(() => expect(right.querySelector('option[value="second-run"]')).toBeTruthy());
  fireEvent.change(right, { target: { value: second.id } });
  fireEvent.click(screen.getByRole("button", { name: "Capture snapshot" }));
  expect(await screen.findByText("snapshot-one")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Primary / left run"), { target: { value: second.id } });
  expect(screen.queryByText("snapshot-one")).toBeNull();
});


it("shows the API validation message when the inspection identifier is invalid", async () => {
  serve(() => json({ detail: [{ msg: "Input should be a valid UUID" }] }, 422));
  render(<Inspection />);
  fireEvent.change(screen.getByLabelText("Inference run ID"), { target: { value: "invalid" } });
  fireEvent.click(screen.getByRole("button", { name: "Load run" }));
  expect((await screen.findAllByText("Input should be a valid UUID")).length).toBeGreaterThan(0);
});
