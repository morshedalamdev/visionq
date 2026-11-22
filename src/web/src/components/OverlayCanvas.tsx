import { useEffect, useRef } from "react";
import type { Detection } from "../api/types";

export function OverlayCanvas({
  source,
  width,
  height,
  detections,
}: {
  source: string;
  width: number;
  height: number;
  detections: Detection[];
}) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const image = new Image();
    image.onload = () => {
      element.width = width;
      element.height = height;
      const context = element.getContext("2d");
      if (!context) return;
      context.clearRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      context.lineWidth = Math.max(2, width / 250);
      context.font = `${Math.max(12, width / 30)}px sans-serif`;
      detections.forEach((detection, index) => {
        const color = ["#ff5d73", "#ffd166", "#36d6c3"][index % 3];
        context.strokeStyle = color;
        context.fillStyle = color;
        context.strokeRect(
          detection.box_xmin,
          detection.box_ymin,
          detection.box_xmax - detection.box_xmin,
          detection.box_ymax - detection.box_ymin,
        );
        context.fillRect(
          detection.box_xmin,
          Math.max(0, detection.box_ymin - 18),
          Math.min(width - detection.box_xmin, 170),
          18,
        );
        context.fillStyle = "#0b1220";
        context.fillText(
          `${detection.class_name} ${(detection.confidence * 100).toFixed(1)}%`,
          detection.box_xmin + 3,
          Math.max(14, detection.box_ymin - 3),
        );
      });
    };
    image.src = source;
  }, [source, width, height, detections]);

  return (
    <canvas
      ref={canvas}
      className="overlay-canvas"
      aria-label={`Image with ${detections.length} persisted detections`}
    />
  );
}
