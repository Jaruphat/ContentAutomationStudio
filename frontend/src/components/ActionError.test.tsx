import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ActionError from "./ActionError";

function axiosError(detail: string, status = 409) {
  return { isAxiosError: true, response: { status, data: { detail } } };
}

describe("ActionError", () => {
  it("surfaces the backend reason rather than a generic failure label", () => {
    const html = renderToStaticMarkup(
      <ActionError
        label="Render plan"
        error={axiosError("Timeline contains stale or mismatched take lineage")}
      />,
    );

    expect(html).toContain("Render plan");
    expect(html).toContain("Timeline contains stale or mismatched take lineage");
    expect(html).toContain('role="alert"');
  });

  it("names an unreachable backend instead of blaming the action", () => {
    const html = renderToStaticMarkup(
      <ActionError
        label="Export"
        error={{ isAxiosError: true, response: undefined }}
      />,
    );

    expect(html).toContain("Could not reach");
  });

  it("renders nothing when the action did not fail", () => {
    expect(
      renderToStaticMarkup(<ActionError label="Build timeline" error={null} />),
    ).toBe("");
  });
});
