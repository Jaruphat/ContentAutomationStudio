import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import CompositeEditor from "./CompositeEditor";
import type { Take } from "../types";

function render() {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  const take = { id: "take-1", shot_id: "shot-1" } as Take;
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <CompositeEditor take={take} />
    </QueryClientProvider>,
  );
}

describe("Composite editor", () => {
  it("asks for the first corner before anything else", () => {
    const html = render();
    expect(html).toContain("Click the top left corner");
  });

  it("shows the frame the layers will be drawn on", () => {
    expect(render()).toContain("/api/media/takes/take-1/file");
  });

  it("offers the patch, because a model writes a smear where a blank was asked for", () => {
    expect(render()).toContain("Cover what is under it");
  });

  it("says the composite is a new take, not an edit of this one", () => {
    const html = render();
    expect(html).toContain("new take of the same shot");
    expect(html).toContain("is not changed");
  });

  it("cannot be applied before the corners and the text exist", () => {
    expect(render()).toContain("disabled");
  });
});
