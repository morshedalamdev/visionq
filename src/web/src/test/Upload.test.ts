import { validateImageFile } from "../features/Upload";
import { describe, expect, it } from "vitest";

describe("upload validation", () => {
  it("accepts PNG and JPEG within the byte limit", () => {
    expect(
      validateImageFile(new File(["image"], "sample.png", { type: "image/png" })),
    ).toBeNull();
    expect(
      validateImageFile(new File(["image"], "sample.jpg", { type: "image/jpeg" })),
    ).toBeNull();
  });

  it("rejects unsafe media and oversized files", () => {
    expect(
      validateImageFile(new File(["svg"], "sample.svg", { type: "image/svg+xml" })),
    ).toMatch(/PNG and JPEG/);
    const oversized = new File(["x"], "large.png", { type: "image/png" });
    Object.defineProperty(oversized, "size", { value: 20_000_001 });
    expect(validateImageFile(oversized)).toMatch(/20 MB/);
  });
});
