/**
 * The text that is pasted into YouTube.
 *
 * The publish package could be read in the gate and written only by posting to
 * the API, so both delivered episodes had their title, series, description and
 * hashtags set from a Python file. A creator using the application had a
 * finished film and no way to name it.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import PublishGate from "./PublishGate";
import type { PublishPackage } from "../types";

const PACKAGE = {
  project_id: "p-1",
  ready: false,
  blockers: ["No render has been made yet."],
  warnings: [],
  publish_title: "The Extra Room",
  series_label: "Strange Floors",
  publish_description: "A caretaker counts the landings.",
  publish_hashtags: "#shorts",
  duration_sec: 32,
  width: 1080,
  height: 1920,
} as unknown as PublishPackage;

function render(pkg: PublishPackage | undefined = PACKAGE) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["quality-rubric"], []);
  qc.setQueryData(["quality-review", "p-1"], null);
  if (pkg) qc.setQueryData(["publish-package", "p-1"], pkg);
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <PublishGate projectId="p-1" />
    </QueryClientProvider>,
  );
}

describe("Publication copy", () => {
  it("can be typed rather than only read", () => {
    const html = render();
    expect(html).toContain('aria-label="Published title"');
    expect(html).toContain('aria-label="Series label"');
    expect(html).toContain('aria-label="Published description"');
    expect(html).toContain('aria-label="Published hashtags"');
  });

  it("starts from what the package already holds", () => {
    const html = render();
    expect(html).toContain("The Extra Room");
    expect(html).toContain("Strange Floors");
    expect(html).toContain("A caretaker counts the landings.");
  });

  it("is offered before the gate passes, not after", () => {
    // Naming the film is part of finishing it. Waiting for a green gate would
    // mean the last thing a creator does has to happen somewhere else.
    expect(render()).toContain("Not ready to publish");
    expect(render()).toContain("Publication copy");
  });

  it("has nothing to save until something is changed", () => {
    expect(render()).toContain("disabled");
  });
});
