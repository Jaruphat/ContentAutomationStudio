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

const status = {
  shot_id: "shot-2", mode: "start_frame", source_take_id: "take-image",
  source_type: "approved_image_take",
  source_shot_id: "shot-1", source_shot_label: "Shot 1", problems: ["The source take is out of date."],
  frame: { id: "frame-image", project_id: "project-1", take_id: "take-image", shot_id: "shot-1",
    reference_image_id: "image-1", frame_time_sec: 0, selection: "source_image", source_type: "approved_image_take", sha256: "image-sha",
    width: 1280, height: 720, source_duration_sec: 0, url: "/scene-image.png",
    created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z" },
  candidates: [{ take_id: "take-image", shot_id: "shot-1", shot_label: "Shot 1", scene_id: "scene-1",
    source_type: "approved_image_take", source_label: "Approved scene image",
    usable: true, reason: "", frame: { id: "frame-image", project_id: "project-1", take_id: "take-image", shot_id: "shot-1",
      reference_image_id: "image-1", frame_time_sec: 0, selection: "source_image", source_type: "approved_image_take", sha256: "image-sha",
      width: 1280, height: 720, source_duration_sec: 0, url: "/scene-image.png",
      created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z" } },
    { take_id: "take-1", shot_id: "shot-video", shot_label: "Shot 0", scene_id: "scene-1",
    source_type: "approved_video_end_frame", source_label: "Previous approved video end frame",
    usable: true, reason: "", frame: { id: "frame-1", project_id: "project-1", take_id: "take-1", shot_id: "shot-video",
      reference_image_id: "image-1", frame_time_sec: 4.8, selection: "last", sha256: "frame-sha",
      width: 1280, height: 720, source_duration_sec: 5, url: "/frame.png",
      created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z" } },
    { take_id: "take-x", shot_id: "shot-x", shot_label: "Shot 9", scene_id: "scene-x", usable: false,
      source_type: "approved_video_end_frame", source_label: "Previous approved video end frame",
      reason: "The source take is no longer approved.", frame: { id: "frame-x", project_id: "project-1", take_id: "take-x", shot_id: "shot-x", reference_image_id: null,
        frame_time_sec: 2, selection: "last", sha256: "x", width: 0, height: 0, source_duration_sec: 2,
        url: null, created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z" } }],
} as unknown as ShotContinuityStatus;

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
    expect(html).toContain("Use approved scene image as start frame");
    expect(html).toContain("Use previous approved video end frame");
    expect(html).toContain("Approved scene image · Shot 1");
    expect(html).toContain("Previous approved video end frame · Shot 0");
    expect(html).toContain("Shot 1");
    expect(html).toContain("Exact approved scene image · start at 0.00s");
    expect(html).toContain("Re-capture approved image");
    expect(html).toContain("Clear continuity");
    expect(html).toContain("Preflight blocker");
    expect(html).toContain("The source take is out of date.");
    expect(html).not.toContain("value=\"take-x\"");
  });
});

describe("the frame a clip has to land on", () => {
  const landing = {
    ...status,
    problems: [],
    end_frame_take_id: "take-land",
    end_frame_shot_id: "shot-3",
    end_frame_shot_label: "Shot 3",
    end_frame: {
      id: "frame-land", project_id: "project-1", take_id: "take-land", shot_id: "shot-3",
      reference_image_id: "image-land", frame_time_sec: 0, selection: "source_image",
      source_type: "approved_image_take", sha256: "landingsha256", width: 864, height: 480,
      source_duration_sec: 0, url: "/landing.png",
      created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:01:00Z",
    },
  } as unknown as ShotContinuityStatus;

  function render(value: ShotContinuityStatus) {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    client.setQueryData(["continuity", "project-1", "scene-1", "shot-2"], value);
    return renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <ShotContinuityControls projectId="project-1" sceneId="scene-1" shotId="shot-2" />
      </QueryClientProvider>,
    );
  }

  it("offers the landing as its own choice, separate from the start frame", () => {
    // Both ends are bound separately because they are separate decisions: a
    // shot often continues from one clip and has to meet a different one.
    const html = render({ ...status, problems: [], end_frame_take_id: null, end_frame: null } as unknown as ShotContinuityStatus);
    expect(html).toContain("End frame");
    expect(html).toContain("Use as the frame this clip lands on");
  });

  it("shows which shot the landing came from, and its hash", () => {
    const html = render(landing);
    expect(html).toContain("Shot 3");
    expect(html).toContain("landingsha");
    expect(html).toContain("Clear end frame");
  });
});
