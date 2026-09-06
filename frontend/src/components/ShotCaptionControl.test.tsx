import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ShotCaptionControl from "./ShotCaptionControl";
import type { Shot } from "../types";

function render(shot: Partial<Shot>) {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  const full = { id: "shot", scene_id: "scene", ...shot } as Shot;
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <ShotCaptionControl shot={full} projectId="project" />
    </QueryClientProvider>,
  );
}

describe("Shot captions", () => {
  it("shows both tracks with what the shot already carries", () => {
    const html = render({
      dialogue: "There's a door at the end of the upstairs hall.",
      emphasis_text: "A DOOR AT THE END.",
    });
    expect(html).toContain("There&#x27;s a door at the end");
    expect(html).toContain("A DOOR AT THE END.");
    expect(html.indexOf("Spoken line")).toBeLessThan(html.indexOf("Emphasis card"));
  });

  it("warns when a card is too long to read at a glance", () => {
    const html = render({
      emphasis_text: "He opened the door at the end of the upstairs hallway",
    });
    expect(html).toContain("A card is held over");
  });

  it("counts a two-line card by its words, not its slash", () => {
    expect(render({ emphasis_text: "SEVEN ROOMS. / SIX ON THE PLAN." })).not.toContain(
      "A card is held over",
    );
  });

  it("says these do not invalidate a generated clip", () => {
    expect(render({ dialogue: "A line." })).toContain("does not put a clip already");
  });
});
