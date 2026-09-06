import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import WorkflowsPage from "./WorkflowsPage";
import type { Workflow } from "../types";

function render() {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WorkflowsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Workflows", () => {
  it("says that nothing can be generated until a workflow is registered", () => {
    expect(render()).toContain("until a workflow is registered");
  });

  it("tells the user which ComfyUI export to take", () => {
    const html = render();
    expect(html).toContain("Export (API)");
    expect(html).toContain("cannot be executed");
  });

  it("takes a file rather than pasted JSON", () => {
    expect(render()).toContain('type="file"');
  });

  it("cannot register without a name and a file", () => {
    expect(render()).toContain("disabled");
  });
});

describe("A mapping this page did not write", () => {
  /**
   * Found while producing an episode. The graph two delivered episodes were
   * made with maps `samplerCfg`, which is not one of the twelve fields this
   * page lists. Saving rebuilt the mapping from the list alone, so the field
   * was dropped - and because a constant was fixed on it, the save was
   * refused with "samplerCfg is fixed as a constant but is not mapped", which
   * was true and unhelpful.
   */
  const withExtra = {
    id: "wf-9",
    name: "Boogu Edit INT8 (1 ref, guidance 9)",
    purpose: "image",
    source_format: "api",
    validation_status: "valid",
    frame_rate: 0,
    constants: { samplerCfg: 9 },
    output_mapping: [],
    parameter_mapping: {
      positivePrompt: { nodeId: "6", field: "text" },
      samplerCfg: { nodeId: "45:3", field: "cfg" },
    },
  } as unknown as Workflow;

  it("shows a mapped field the page has never heard of", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    qc.setQueryData(["workflows"], [withExtra]);
    const html = renderToStaticMarkup(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <WorkflowsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(html).toContain("samplerCfg");
    expect(html).toContain('value="45:3"');
  });
});
