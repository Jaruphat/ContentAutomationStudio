import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ShotCharacterBinding, ShotContinuityControls } from "./ShotContinuityControls";
import type { CharacterSet, ShotContinuityStatus } from "../types";

const sets = [
  { id: "current", name: "Ari", approved_version_id: "v1", approved_version_is_current: true },
  { id: "stale", name: "Bo", approved_version_id: "v2", approved_version_is_current: false },
  { id: "draft", name: "Cy", approved_version_id: null, approved_version_is_current: false },
] as CharacterSet[];

const status: ShotContinuityStatus = {
  shot_id: "shot-2", mode: "previous_approved_end_frame", source_take_id: "take-1",
  source_shot_id: "shot-1", source_shot_label: "Shot 1", problems: ["The source take is out of date."],
  frame: { id: "frame-1", project_id: "project-1", take_id: "take-1", shot_id: "shot-1",
    reference_image_id: "image-1", frame_time_sec: 4.8, selection: "last", sha256: "frame-sha",
    width: 1280, height: 720, source_duration_sec: 5, url: "/frame.png",
    created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z" },
  candidates: [{ take_id: "take-1", shot_id: "shot-1", shot_label: "Shot 1", scene_id: "scene-1",
    usable: true, reason: "", frame: { id: "frame-1", project_id: "project-1", take_id: "take-1", shot_id: "shot-1",
      reference_image_id: "image-1", frame_time_sec: 4.8, selection: "last", sha256: "frame-sha",
      width: 1280, height: 720, source_duration_sec: 5, url: "/frame.png",
      created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z" } },
    { take_id: "take-x", shot_id: "shot-x", shot_label: "Shot 9", scene_id: "scene-x", usable: false,
      reason: "The source take is no longer approved.", frame: { id: "frame-x", project_id: "project-1", take_id: "take-x", shot_id: "shot-x", reference_image_id: null,
        frame_time_sec: 2, selection: "last", sha256: "x", width: 0, height: 0, source_duration_sec: 2,
        url: null, created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z" } }],
};

function wrapper(children: React.ReactNode) {
  return renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>);
}

describe("shot character and continuity controls", () => {
  it("offers only approved/current sets while naming stale existing bindings", () => {
    const html = wrapper(<ShotCharacterBinding sets={sets} assignedIds={["current", "stale"]} onChange={() => {}} />);
    expect(html).toContain("Ari");
    expect(html).toContain("Bo · stale approved version");
    expect(html).not.toContain("Cy");
    expect(html).toContain("Only approved, current character sets can be added");
  });

  it("requires an explicit related take choice and surfaces extraction and preflight state", () => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    client.setQueryData(["continuity", "project-1", "scene-2", "shot-2"], status);
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><ShotContinuityControls projectId="project-1" sceneId="scene-2" shotId="shot-2" /></QueryClientProvider>);
    expect(html).toContain("Use previous approved shot end frame");
    expect(html).toContain("Choose an eligible previous approved video take");
    expect(html).toContain("Shot 1");
    expect(html).toContain("Extracted at 4.80s");
    expect(html).toContain("Re-extract end frame");
    expect(html).toContain("Clear continuity");
    expect(html).toContain("Preflight blocker");
    expect(html).toContain("The source take is out of date.");
    expect(html).not.toContain("value=\"take-x\"");
  });
});
