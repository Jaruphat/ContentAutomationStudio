import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import WorkflowsPage from "./WorkflowsPage";

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
