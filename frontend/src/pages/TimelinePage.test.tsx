import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import TimelinePage, { currentProjectValue } from "./TimelinePage";
import type { RenderPlan, RenderResult, TimelineItem, TimelineManifest } from "../types";

vi.mock("../store/useProjectStore", () => ({
  useAppState: () => ({ currentProjectId: "project-1" }),
}));

const TIMELINE_KEY = ["timeline", "project-1"];

describe("Timeline project isolation", () => {
  it("hides a render plan that belongs to a previously selected project", () => {
    const plan = { project_id: "project-a" } as RenderPlan;

    expect(currentProjectValue({ projectId: "project-a", data: plan }, "project-b")).toBeNull();
  });

  it("hides a late render result that belongs to a previously selected project", () => {
    const result = { project_id: "project-a" } as RenderResult;

    expect(currentProjectValue({ projectId: "project-a", data: result }, "project-b")).toBeNull();
  });
});

function queryClient() {
  return new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
}

function item(overrides: Partial<TimelineItem> = {}): TimelineItem {
  return {
    id: "item-1",
    project_id: "project-1",
    shot_id: "shot-12345678",
    take_id: "take-12345678",
    order: 0,
    in_point_sec: 0,
    out_point_sec: 4,
    duration_sec: 4,
    transition_in: "cut",
    transition_out: "cut",
    created_at: "2026-09-03T00:00:00Z",
    updated_at: "2026-09-03T00:00:00Z",
    scene_id: "scene-1",
    scene_title: "The Race Begins",
    shot_name: "Shot 2 - Rabbit sprinting along the dirt path",
    thumbnail_url: null,
    waived: false,
    ...overrides,
  };
}

function manifest(overrides: Partial<TimelineManifest> = {}): TimelineManifest {
  return {
    project_id: "project-1",
    items: [],
    total_duration_sec: 0,
    item_count: 0,
    warnings: [],
    delivery_validation: { pipeline_pass: true, delivery_spec_pass: true },
    coverage: { total_shots: 0, covered_shots: 0, missing: [] },
    ...overrides,
  };
}

function render(qc: QueryClient) {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={["/timeline"]}>
      <QueryClientProvider client={qc}>
        <TimelinePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function renderManifest(data: TimelineManifest) {
  const qc = queryClient();
  qc.setQueryData(TIMELINE_KEY, data);
  return render(qc);
}

/**
 * A QueryClient whose cached error is not immediately clobbered by a
 * refetch-on-mount. `retryOnMount` defaults to true, so as soon as
 * TimelinePage's own `useQuery` observer mounts on an already-errored query it
 * would otherwise trigger a fresh fetch - which, because the query has no
 * data, resets status to "pending" before `renderToStaticMarkup` ever
 * captures the error state being tested here.
 */
function erroredQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        enabled: false,
        retry: false,
        retryOnMount: false,
        staleTime: Infinity,
      },
    },
  });
}

/** Puts the timeline query into the error state the backend really returns. */
async function renderWithTimelineError(detail: string, status = 409) {
  const qc = erroredQueryClient();
  await qc.prefetchQuery({
    queryKey: TIMELINE_KEY,
    retry: false,
    queryFn: () =>
      Promise.reject({
        isAxiosError: true,
        response: { status, data: { detail } },
      }),
  });
  return render(qc);
}

const override = {
  code: "e2e_aspect_override",
  message: "E2E Override · Aspect mismatch accepted · user-approved test override",
  take_ids: ["take-1"],
  waived_from_take_ids: ["source-take"],
  waiver_reasons: ["User-approved E2E dimension exception"],
};

describe("Timeline E2E override truthfulness", () => {
  it("shows a prominent warning and separates pipeline from delivery-spec pass", () => {
    const html = renderManifest(
      manifest({
        warnings: [override],
        delivery_validation: { pipeline_pass: true, delivery_spec_pass: false },
      }),
    );

    expect(html).toContain(override.message);
    expect(html).toContain("Pipeline pass");
    expect(html).toContain("Delivery spec not passed");
    expect(html).toContain("1 waived take");
  });

  it("does not show an override banner without backend warning metadata", () => {
    const html = renderManifest(manifest());

    expect(html).not.toContain("E2E Override");
    expect(html).not.toContain("Delivery spec not passed");
  });

  it("marks the individual rows whose take was waived", () => {
    const html = renderManifest(
      manifest({
        items: [
          item({ id: "a", waived: true }),
          item({ id: "b", take_id: "take-2", waived: false }),
        ],
        item_count: 2,
        total_duration_sec: 8,
      }),
    );

    expect(html.match(/Waived/g)?.length).toBe(1);
  });
});

describe("Timeline readability", () => {
  it("names the scene and shot on every row instead of truncated ids", () => {
    const html = renderManifest(
      manifest({ items: [item()], item_count: 1, total_duration_sec: 4 }),
    );

    expect(html).toContain("The Race Begins");
    expect(html).toContain("Shot 2 - Rabbit sprinting along the dirt path");
  });

  it("shows the take thumbnail when the backend published a servable one", () => {
    const html = renderManifest(
      manifest({
        items: [item({ thumbnail_url: "/api/media/takes/take-1/file" })],
        item_count: 1,
      }),
    );

    expect(html).toContain('src="/api/media/takes/take-1/file"');
  });

  it("counts the items and offers Export as the next step", () => {
    const html = renderManifest(
      manifest({
        items: [item(), item({ id: "item-2" })],
        item_count: 2,
        total_duration_sec: 8.5,
        coverage: { total_shots: 2, covered_shots: 2, missing: [] },
      }),
    );

    expect(html).toContain("2 items");
    expect(html).toContain("8.5s");
    expect(html).toMatch(/href="\/export"/);
  });
});

describe("Timeline coverage truthfulness", () => {
  it("says which shots the build left out and what to do about each", () => {
    const html = renderManifest(
      manifest({
        items: [item()],
        item_count: 1,
        coverage: {
          total_shots: 3,
          covered_shots: 1,
          missing: [
            {
              shot_id: "shot-2",
              scene_id: "scene-1",
              scene_title: "A New Finish",
              shot_name: "Shot 1 - Tortoise crossing the line",
              shot_order: 1,
              reason: "Takes are waiting in Review; approve one to place this shot.",
            },
            {
              shot_id: "shot-3",
              scene_id: "scene-1",
              scene_title: "A New Finish",
              shot_name: "Shot 2 - Wide of the forest path",
              shot_order: 2,
              reason: "No take has been generated for this shot yet.",
            },
          ],
        },
      }),
    );

    expect(html).toContain("1 of 3 shots");
    expect(html).toContain("Shot 1 - Tortoise crossing the line");
    expect(html).toContain("Takes are waiting in Review");
    expect(html).toContain("No take has been generated for this shot yet.");
    expect(html).toMatch(/href="\/review"/);
  });

  it("does not nag about coverage when every shot is on the cut", () => {
    const html = renderManifest(
      manifest({
        items: [item()],
        item_count: 1,
        coverage: { total_shots: 1, covered_shots: 1, missing: [] },
      }),
    );

    expect(html).not.toContain("not on the timeline");
  });
});

describe("Timeline failure truthfulness", () => {
  it("keeps rendering when a running backend still returns the legacy timeline shape", () => {
    const legacy = manifest({
      items: [item()],
      item_count: 1,
      total_duration_sec: 4,
    }) as Partial<TimelineManifest>;
    delete legacy.warnings;
    delete legacy.delivery_validation;
    delete legacy.coverage;

    const html = renderManifest(legacy as TimelineManifest);

    expect(html).toContain("The Race Begins");
    expect(html).toContain("1 item");
    expect(html).not.toContain("E2E Override");
  });

  it("explains a refused timeline read instead of rendering an empty page", async () => {
    const html = await renderWithTimelineError(
      "Timeline contains stale or mismatched take lineage in item(s): item-1",
    );

    expect(html).toContain("stale or mismatched take lineage");
    expect(html).toContain("Rebuild timeline");
    // The empty state would tell the user the opposite of what happened.
    expect(html).not.toContain("No timeline items yet");
  });

  it("reports an unreachable backend rather than an empty timeline", async () => {
    const qc = erroredQueryClient();
    await qc.prefetchQuery({
      queryKey: TIMELINE_KEY,
      retry: false,
      queryFn: () => Promise.reject({ isAxiosError: true, response: undefined }),
    });

    const html = render(qc);

    expect(html).toContain("Could not reach");
    expect(html).not.toContain("No timeline items yet");
  });

});
