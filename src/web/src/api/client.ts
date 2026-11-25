import type {
  AgentFixture,
  ApiList,
  Batch,
  ContextSnapshot,
  Comparison,
  Dataset,
  DatasetSummary,
  ImageResult,
  InferenceRun,
  RunDetail,
  UploadRequest,
} from "./types";

const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";
const token = (import.meta.env.VITE_API_TOKEN as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  if (!token) {
    throw new ApiError(
      503,
      "VITE_API_TOKEN is not configured. The API is intentionally unavailable.",
    );
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        const first = body.detail[0];
        if (typeof first?.msg === "string") message = first.msg;
      }
    } catch {
      // Keep the bounded status message.
    }
    throw new ApiError(response.status, message);
  }
  return response;
}

async function getJson<T>(path: string): Promise<T> {
  return (await request(path)).json() as Promise<T>;
}

export const api = {
  datasets: (offset = 0) => getJson<ApiList<Dataset>>(`/app/datasets?limit=100&offset=${offset}`),
  dataset: (id: string) => getJson<DatasetSummary>(`/app/datasets/${id}`),
  batches: (datasetId?: string, offset = 0) =>
    getJson<ApiList<Batch>>(
      `/app/batches?limit=100&offset=${offset}${
        datasetId ? `&dataset_version_id=${encodeURIComponent(datasetId)}` : ""
      }`,
    ),
  runs: (
    datasetId?: string,
    batchId?: string,
    filters?: {
      status?: string;
      modelId?: string;
      createdAfter?: string;
      createdBefore?: string;
    },
    offset = 0,
  ) => {
    const query = new URLSearchParams({ limit: "100", offset: String(offset) });
    if (datasetId) query.set("dataset_version_id", datasetId);
    if (batchId) query.set("batch_id", batchId);
    if (filters?.status) query.set("status", filters.status);
    if (filters?.modelId) query.set("model_id", filters.modelId);
    if (filters?.createdAfter) {
      query.set("created_after", `${filters.createdAfter}T00:00:00Z`);
    }
    if (filters?.createdBefore) {
      query.set("created_before", `${filters.createdBefore}T23:59:59.999999Z`);
    }
    return getJson<ApiList<InferenceRun>>(`/app/runs?${query}`);
  },
  run: (id: string) => getJson<RunDetail>(`/app/runs/${id}`),
  runImages: (id: string, offset = 0) =>
    getJson<ApiList<ImageResult>>(`/app/runs/${id}/images?limit=100&offset=${offset}`),
  snapshot: (
    datasetId: string,
    runs: Pick<InferenceRun, "id" | "batch_id">[],
    metricNames: string[],
  ) => {
    const scopes = runs.map((run, index) => ({
      role: runs.length === 2 ? (index === 0 ? "left" : "right") : "primary",
      dataset_version_id: datasetId,
      batch_id: run.batch_id,
      inference_run_id: run.id,
    }));
    return request("/analytics/context-snapshots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scopes, metric_names: metricNames }),
    }).then((response) => response.json() as Promise<ContextSnapshot>);
  },
  compare: (snapshotId: string, metricNames: string[]) =>
    request(`/analytics/context-snapshots/${snapshotId}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metricNames),
    }).then(
      (response) =>
        response.json() as Promise<{ metrics: Comparison[] }>,
    ),
  upload: (file: File, datasetId?: string, batchId?: string) => {
    const body = new FormData();
    body.set("file", file);
    if (datasetId) body.set("dataset_version_id", datasetId);
    if (batchId) body.set("batch_id", batchId);
    return request("/app/uploads", { method: "POST", body }).then(
      (response) => response.json() as Promise<UploadRequest>,
    );
  },
  uploads: (offset = 0) => getJson<ApiList<UploadRequest>>(`/app/uploads?limit=100&offset=${offset}`),
  artifactUrl: async (url: string) => {
    const response = await request(url);
    return URL.createObjectURL(await response.blob());
  },
  agentFixture: () => getJson<AgentFixture>("/app/agent-fixture"),
};
