import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RunProgressBar from "./RunProgressBar";
import type { GenerationJob } from "../types";

/**
 * A shot takes minutes on local hardware, and the stage a user is looking at
 * is usually not the Generate page. Without a persistent line there is no way
 * to tell a slow render from a stuck one without opening ComfyUI.
 */
const job = (over: Partial<GenerationJob>): GenerationJob => ({
  id: "job-1", shot_id: "shot-1", run_id: "run-1", workflow_id: "wf",
  workflow_version: "1", workflow_snapshot_path: null, workflow_sha256: null,
  parameter_map: {}, status: "Running", progress: 0, progress_stage: "",
  ...over,
} as GenerationJob);

function render(jobs: GenerationJob[], shots: Record<string, string> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  client.setQueryData(["jobs", "project-1"], jobs);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <RunProgressBar projectId="project-1" shotLabels={shots} />
    </QueryClientProvider>,
  );
}

describe("RunProgressBar", () => {
  it("says nothing at all when nothing is running", () => {
    // An always-present empty bar is just clutter on a finished project.
    expect(render([job({ status: "Completed", progress: 1 })])).toBe("");
  });

  it("names the shot being generated, not just the job id", () => {
    const html = render(
      [job({ status: "Running", progress: 0.375, progress_stage: "step 3 of 8 in KSampler" })],
      { "shot-1": "Scene 2 · Shot 3" },
    );
    expect(html).toContain("Scene 2 · Shot 3");
  });

  it("shows the provider's own stage and percentage", () => {
    const html = render([
      job({ status: "Running", progress: 0.375, progress_stage: "step 3 of 8 in KSampler" }),
    ]);
    expect(html).toContain("step 3 of 8 in KSampler");
    expect(html).toContain("38%");
  });

  it("reports how many are still waiting behind it", () => {
    const html = render([
      job({ id: "a", status: "Running", progress: 0.5 }),
      job({ id: "b", status: "Queued" }),
      job({ id: "c", status: "Queued" }),
    ]);
    expect(html).toContain("2 queued");
  });

  it("falls back to plain running when the provider will not say a stage", () => {
    // Better an honest "running" than a percentage nothing measured.
    const html = render([job({ status: "Running", progress: 0, progress_stage: "" })]);
    expect(html).toContain("Running");
    expect(html).not.toContain("%");
  });
});
