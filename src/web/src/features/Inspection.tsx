import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ImageResult, RunDetail } from "../api/types";
import { Badge, ErrorState, LoadingState } from "../components/AsyncState";
import { OverlayCanvas } from "../components/OverlayCanvas";

export function Inspection({ initialRunId = "" }: { initialRunId?: string }) {
  const [runId, setRunId] = useState(initialRunId);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [images, setImages] = useState<ImageResult[]>([]);
  const [selected, setSelected] = useState<ImageResult | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!initialRunId) return;
    setRunId(initialRunId);
  }, [initialRunId]);

  const load = () => {
    if (!runId.trim()) return;
    setLoading(true);
    setError(null);
    Promise.all([api.run(runId), api.runImages(runId)])
      .then(([detail, result]) => {
        setRun(detail);
        setImages(result.items);
        setSelected(result.items[0] ?? null);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!selected) {
      setImageUrl("");
      return;
    }
    let active = true;
    let objectUrl = "";
    api.artifactUrl(selected.image_url)
      .then((url) => {
        if (!active) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setImageUrl(url);
      })
      .catch(setError);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selected]);

  return (
    <section>
      <header className="page-header"><div><span className="eyebrow">Stored predictions</span><h1>Image inspection</h1><p>Original-coordinate persisted boxes are rendered without client-side coordinate conversion.</p></div></header>
      <div className="panel input-row">
        <label>Inference run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="Paste a persisted run UUID" /></label>
        <button onClick={load}>Load run</button>
      </div>
      {loading ? <LoadingState label="Loading persisted run" /> : null}
      {error ? <ErrorState error={error} retry={load} /> : null}
      {run ? (
        <>
          <div className="panel provenance-strip">
            <div><small>Dataset</small><strong>{run.dataset_name} v{run.dataset_release}</strong></div>
            <div><small>Split</small><strong>{run.batch_split ?? "unavailable"}</strong></div>
            <div><small>Model</small><strong>{run.architecture}</strong></div>
            <Badge value={run.evidence_kind} /><Badge value={run.status} />
          </div>
          <div className="inspection-layout">
            <div className="panel image-strip">
              {images.map((image) => (
                <button key={image.asset_id} className={selected?.asset_id === image.asset_id ? "selected" : ""} onClick={() => setSelected(image)}>
                  <strong>{image.asset_id.slice(0, 8)}</strong>
                  <Badge value={image.status} />
                  <small>{image.detection_count ?? "—"} boxes</small>
                </button>
              ))}
            </div>
            <div className="panel inspection-main">
              {selected && imageUrl ? <OverlayCanvas source={imageUrl} width={selected.width} height={selected.height} detections={selected.detections} /> : <p>Select an image with a readable artifact.</p>}
              {selected ? (
                <div className="detection-list">
                  <h3>Persisted detections</h3>
                  {selected.status !== "succeeded" ? <p>{selected.status}. {selected.last_error ?? "No predictions are available."}</p> : null}
                  {selected.status === "succeeded" && !selected.detections.length ? <p>Successful zero-detection result.</p> : null}
                  {selected.detections.map((detection) => (
                    <div key={detection.ordinal}>
                      <strong>{detection.class_name}</strong>
                      <span>{(detection.confidence * 100).toFixed(1)}% confidence</span>
                      <code>[{detection.box_xmin}, {detection.box_ymin}, {detection.box_xmax}, {detection.box_ymax}]</code>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
