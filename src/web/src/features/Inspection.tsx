import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ImageResult, RunDetail } from "../api/types";
import { Badge, ErrorState, LoadingState } from "../components/AsyncState";
import { OverlayCanvas } from "../components/OverlayCanvas";

import { usePage } from "../api/usePage";
import { PageControls } from "../components/PageControls";

export function Inspection({ initialRunId = "" }: { initialRunId?: string }) {
  const [runId, setRunId] = useState(initialRunId);
  const [loadedId, setLoadedId] = useState(initialRunId);
  return (
    <section>
      <header className="page-header"><div><span className="eyebrow">Stored predictions</span><h1>Image inspection</h1><p>Original-coordinate persisted boxes are rendered without client-side coordinate conversion.</p></div></header>
      <div className="panel input-row">
        <label>Inference run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="Paste a persisted run UUID" /></label>
        <button onClick={() => setLoadedId(runId.trim())} disabled={!runId.trim()}>Load run</button>
      </div>
      {loadedId && <RunInspection key={loadedId} runId={loadedId} />}
    </section>
  );
}

function RunInspection({ runId }: { runId: string }) {
  const [revision, setRevision] = useState(0);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<unknown>();
  const [assetId, setAssetId] = useState("");
  const images = usePage(useCallback((offset: number) => api.runImages(runId, offset), [runId]));
  const selected = images.items.find(image => image.asset_id === assetId) ?? images.items[0];
  useEffect(() => {
    let active = true;
    setError(null);
    api.run(runId).then(
      data => { if (active) setRun(data); },
      reason => { if (active) setError(reason); },
    );
    return () => { active = false; };
  }, [runId, revision]);

  return (<>
      {!run && !error ? <LoadingState label="Loading persisted run" /> : null}
      {error ? <ErrorState error={error} retry={() => setRevision(revision + 1)} /> : null}
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
              <PageControls page={images} label="images" />
              {images.items.map((image) => (
                <button key={image.asset_id} className={selected?.asset_id === image.asset_id ? "selected" : ""} onClick={() => setAssetId(image.asset_id)}>
                  <strong>{image.asset_id.slice(0, 8)}</strong>
                  <Badge value={image.status} />
                  <small>{image.detection_count ?? "—"} boxes</small>
                </button>
              ))}
            </div>
            <div className="panel inspection-main">
              {selected ? <ImageOverlay key={selected.image_url} image={selected} /> : <p>Select an image with a readable artifact.</p>}
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
    </>
  );
}

function ImageOverlay({ image }: { image: ImageResult }) {
  const [source, setSource] = useState("");
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    let active = true;
    let current = "";
    api.artifactUrl(image.image_url).then(
      url => {
        if (active) {
          current = url;
          setSource(url);
        } else URL.revokeObjectURL(url);
      },
      reason => { if (active) setError(reason); },
    );
    return () => {
      active = false;
      if (current) URL.revokeObjectURL(current);
    };
  }, [image.image_url]);

  if (error) return <ErrorState error={error} />;
  if (!source) return <LoadingState label="Loading image" />;
  return <OverlayCanvas source={source} width={image.width} height={image.height} detections={image.detections} />;
}
