import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import MotionReport from "./MotionReport";
import type { Take } from "../types";

function render(duration: number, report?: object) {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  const take = { id: "take", duration_sec: duration, provenance: report ? { media_analysis: report } : null } as Take;
  return renderToStaticMarkup(<QueryClientProvider client={qc}><MotionReport take={take} projectId="project" /></QueryClientProvider>);
}

describe("Motion review", () => {
  it("does not label an unmeasured clip as motionless", () => {
    const html = render(5);
    expect(html).toContain("has not been measured");
    expect(html).not.toContain("0% near-static");
  });
  it("shows a warning and the limits of a measured result", () => {
    const html = render(5, { status: "measured", mean_luma_change: .25, near_static_fraction: .98, sample_fps: 8, warnings: ["Check the intended action"] });
    expect(html).toContain("98% near-static");
    expect(html).toContain("Check the intended action");
    expect(html).toContain("Cuts and flicker");
    expect(html).not.toContain("Approved");
  });
  it("explains unavailable measurements and skips still images", () => {
    expect(render(5, { status: "unavailable", reason: "FFmpeg is missing" })).toContain("FFmpeg is missing");
    expect(render(0)).toBe("");
  });
});
