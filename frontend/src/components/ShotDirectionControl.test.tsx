import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ShotDirectionControl from "./ShotDirectionControl";
import type { Shot } from "../types";

function render(shot: Partial<Shot>) {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  const full = { id: "shot", scene_id: "scene", ...shot } as Shot;
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <ShotDirectionControl shot={full} projectId="project" />
    </QueryClientProvider>,
  );
}

describe("Clip direction", () => {
  it("offers all three directions in the order they are sent", () => {
    const html = render({
      subject_motion: "The door swings open.",
      camera_motion: "Locked-off camera.",
      audio_direction: "a pneumatic hiss",
    });
    expect(html).toContain("The door swings open.");
    expect(html).toContain("Locked-off camera.");
    expect(html).toContain("a pneumatic hiss");
    expect(html.indexOf("What happens in the frame")).toBeLessThan(
      html.indexOf("How the camera behaves"),
    );
    expect(html.indexOf("How the camera behaves")).toBeLessThan(
      html.indexOf("What it sounds like"),
    );
  });

  it("warns when only the camera is directed", () => {
    const html = render({ subject_motion: "", camera_motion: "Slow drift." });
    expect(html).toContain("only how the camera behaves");
  });

  it("says nothing about the camera when something moves", () => {
    const html = render({
      subject_motion: "Mist drifts.",
      camera_motion: "Slow drift.",
    });
    expect(html).not.toContain("only how the camera behaves");
  });

  it("warns that saving invalidates a clip already generated", () => {
    expect(render({ subject_motion: "Mist drifts." })).toContain("out of date");
  });
});
