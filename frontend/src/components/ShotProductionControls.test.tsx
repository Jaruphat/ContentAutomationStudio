/**
 * The three decisions a shot carries that had no control on any page.
 *
 * Each of them decided something in an episode that was actually delivered,
 * and each was only reachable by posting to the API:
 *
 * * **Which workflow.** Two episodes were re-generated against a graph with a
 *   higher guidance scale so the prompt could move the framing. Choosing that
 *   per shot was a script.
 * * **Whether it reaches the cut.** A key image exists so a clip can be
 *   animated from it. Left in the cut it plays as a still, and a 32-second
 *   film silently became 48 with no error anywhere.
 * * **What must not be in the frame.** Negatives existed only on a style, so
 *   "no text on the newspaper" could not be said about the one shot holding a
 *   newspaper.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ShotProductionControls from "./ShotProductionControls";
import type { Workflow } from "../types";

const WORKFLOWS = [
  { id: "wf-1", name: "H3 I2V — guidance 9" },
  { id: "wf-2", name: "Z-Image Turbo" },
] as unknown as Workflow[];

function render(props: Partial<React.ComponentProps<typeof ShotProductionControls>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["workflows"], WORKFLOWS);
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <ShotProductionControls
        workflowPresetId=""
        includeInCut
        negativePrompt=""
        onChange={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("Shot production controls", () => {
  it("offers every registered workflow by name", () => {
    const html = render();
    expect(html).toContain("H3 I2V — guidance 9");
    expect(html).toContain("Z-Image Turbo");
  });

  it("defaults to the project's workflow rather than naming one", () => {
    expect(render()).toContain("Project default");
  });

  it("shows the workflow a shot has already been given", () => {
    expect(render({ workflowPresetId: "wf-2" })).toContain('value="wf-2"');
  });

  it("shows a shot that is in the cut as checked", () => {
    expect(render()).toContain("checked");
  });

  it("shows a key image as out of the cut", () => {
    expect(render({ includeInCut: false })).not.toContain("checked");
  });

  it("says why a shot would be kept out of the cut", () => {
    expect(render()).toContain("animate");
  });

  it("carries the shot's own negatives", () => {
    expect(render({ negativePrompt: "no text, no lettering" })).toContain(
      "no text, no lettering",
    );
  });
});
