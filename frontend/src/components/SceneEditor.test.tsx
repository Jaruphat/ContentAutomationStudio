/**
 * A scene was readable and not writable.
 *
 * It was created as "Scene 3" and stayed that way: every field the inspector
 * showed - title, summary, purpose, time of day, beat, duration, location,
 * cast - was read-only text, and the only way to write one was to post to the
 * API. Two of them are not labels. `time_of_day` and `summary` reach the
 * compiled prompt, so a scene nobody could edit was a prompt nobody could
 * correct without a terminal.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import SceneEditor from "./SceneEditor";
import type { Character, Location, Scene } from "../types";

const SCENE = {
  id: "sc-1",
  project_id: "p-1",
  order: 3,
  title: "The upstairs hall",
  purpose: "establish the extra door",
  summary: "He counts the landings and finds one more.",
  character_ids: ["ch-1"],
  location_id: "lo-1",
  time_of_day: "night",
  emotional_beat: "unease",
  planned_duration_sec: 8,
  status: "Draft",
} as unknown as Scene;

function render(scene: Scene = SCENE) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["characters", "p-1"], [
    { id: "ch-1", name: "The caretaker" },
    { id: "ch-2", name: "The tenant" },
  ] as unknown as Character[]);
  qc.setQueryData(["locations", "p-1"], [
    { id: "lo-1", name: "Upstairs landing" },
  ] as unknown as Location[]);
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <SceneEditor projectId="p-1" scene={scene} onDone={() => {}} />
    </QueryClientProvider>,
  );
}

describe("Scene editor", () => {
  it("shows the scene's own title rather than its position", () => {
    expect(render()).toContain("The upstairs hall");
  });

  it("carries the two fields that reach the prompt", () => {
    const html = render();
    expect(html).toContain("night");
    expect(html).toContain("He counts the landings and finds one more.");
  });

  it("says which fields the model will read", () => {
    // Otherwise a summary reads like a note to yourself, and a careless one
    // ends up in the picture.
    expect(render()).toContain("Reaches the prompt.");
  });

  it("offers the cast from the story bible rather than a free-text field", () => {
    // A scene naming a character who does not exist is a scene whose prompt
    // silently loses them.
    const html = render();
    expect(html).toContain("The caretaker");
    expect(html).toContain("The tenant");
  });

  it("shows who is already in the scene as chosen", () => {
    expect(render()).toContain('aria-label="The caretaker is in this scene" checked');
  });

  it("offers the locations that exist, and no location as a choice", () => {
    const html = render();
    expect(html).toContain("Upstairs landing");
    expect(html).toContain("Not set");
  });

  it("keeps the scene's planned length editable", () => {
    expect(render()).toContain('value="8"');
  });
});
