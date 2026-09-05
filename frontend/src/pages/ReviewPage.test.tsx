import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ReviewPage, { reviewRunPath } from "./ReviewPage";

vi.mock("../store/useProjectStore", () => ({
  useAppState: () => ({ currentProjectId: "project-1", selectedTakeId: null }),
  useAppDispatch: () => vi.fn(),
}));

function queryClient() {
  return new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
}

function renderPage(qc: QueryClient, path = "/review") {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ReviewPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function take(overrides: Record<string, unknown> = {}) {
  return {
    id: "take-1",
    shot_id: "shot-12345678",
    job_id: "job-1",
    run_id: "run-1",
    file_path: "",
    thumbnail_path: "",
    duration_sec: 0,
    width: 0,
    height: 0,
    frame_rate: 0,
    codec: "",
    media_provider_id: "comfyui",
    media_model: "workflow-v1",
    request_params: null,
    usage: null,
    estimated_cost_usd: null,
    provenance: null,
    review_status: "Pending",
    rating: null,
    notes: "",
    approved_at: null,
    created_at: "2026-09-03T00:00:00Z",
    ...overrides,
  };
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    project_id: "project-1",
    kind: "batch",
    label: "Run 3",
    sequence: 3,
    status: "Completed",
    terminal: true,
    total_jobs: 2,
    queued: 0,
    running: 0,
    completed: 2,
    failed: 0,
    cancelled: 0,
    pending_take_count: 2,
    ready_for_review: true,
    created_at: "2026-09-03T00:00:00Z",
    jobs: [],
    ...overrides,
  };
}

describe("Review run filtering", () => {
  it("makes take cards keyboard selectable and exposes the selected filter", () => {
    const qc = queryClient();
    qc.setQueryData(["takes", "project-1", null], [take()]);

    const html = renderPage(qc);

    expect(html).toMatch(/role="button"[^>]*tabindex="0"/);
    expect(html).toMatch(/aria-pressed="true"[^>]*>All<\/button>/);
  });

  it("follows a regeneration run in the Review URL", () => {
    expect(reviewRunPath("new-run/id")).toBe("/review?run=new-run%2Fid");
  });

  it("scopes the take list to the run named in the URL", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run", "run-1"], run());
    qc.setQueryData(
      ["takes", "project-1", "run-1"],
      [take({ id: "take-in-run" })],
    );
    qc.setQueryData(
      ["takes", "project-1", null],
      [take({ id: "take-in-run" }), take({ id: "take-from-elsewhere" })],
    );

    const html = renderPage(qc, "/review?run=run-1");

    expect(html).toContain("Run 3");
    expect(html).toContain("1 take");
    expect(html).not.toContain("take-from-elsewhere");
  });

  it("offers a clear action that drops the run filter", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run", "run-1"], run());
    qc.setQueryData(["takes", "project-1", "run-1"], [take()]);

    const html = renderPage(qc, "/review?run=run-1");

    expect(html).toContain("Show all takes");
    expect(html).toMatch(/href="\/review"/);
  });

  it("names an unknown run by its id rather than pretending it has none", () => {
    const qc = queryClient();
    qc.setQueryData(["takes", "project-1", "run-9"], [take({ run_id: "run-9" })]);

    const html = renderPage(qc, "/review?run=run-9");

    expect(html).toContain("run-9");
    expect(html).toContain("Show all takes");
  });

  it("shows no run banner when the whole project is being reviewed", () => {
    const qc = queryClient();
    qc.setQueryData(["takes", "project-1", null], [take()]);

    const html = renderPage(qc);

    expect(html).not.toContain("Show all takes");
    expect(html).toContain("1 take");
  });

  it("shows no run banner when the whole project is being reviewed and no take is approved", () => {
    const qc = queryClient();
    qc.setQueryData(["takes", "project-1", null], [take()]);

    const html = renderPage(qc);

    expect(html).not.toMatch(/href="\/timeline"/);
  });

  it("explains an empty run instead of blaming the whole project", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run", "run-1"], run({ pending_take_count: 0 }));
    qc.setQueryData(["takes", "project-1", "run-1"], []);

    const html = renderPage(qc, "/review?run=run-1");

    expect(html).toContain("Run 3");
    expect(html).toContain("No takes");
  });
});


describe("Review hand-off to the timeline", () => {
  it("offers Timeline as the next step once takes are approved", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["takes", "project-1", null],
      [
        take({ id: "a", review_status: "Approved" }),
        take({ id: "b", review_status: "Approved" }),
        take({ id: "c", review_status: "Pending" }),
      ],
    );

    const html = renderPage(qc);

    expect(html).toMatch(/href="\/timeline"/);
    expect(html).toContain("2 approved");
    expect(html).toContain("1 still needs review");
  });

  it("says the review is finished when nothing is left pending", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["takes", "project-1", null],
      [
        take({ id: "a", review_status: "Approved" }),
        take({ id: "b", review_status: "Rejected" }),
      ],
    );

    const html = renderPage(qc);

    expect(html).toContain("Every take has been reviewed");
    expect(html).toContain("Build the timeline");
    expect(html).toMatch(/href="\/timeline"/);
  });

  it("says the run is finished, not the whole project, when scoped to a run", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run", "run-1"], run());
    qc.setQueryData(
      ["takes", "project-1", "run-1"],
      [
        take({ id: "a", review_status: "Approved", run_id: "run-1" }),
        take({ id: "b", review_status: "Rejected", run_id: "run-1" }),
      ],
    );

    const html = renderPage(qc, "/review?run=run-1");

    expect(html).toContain("This run is fully reviewed");
    expect(html).not.toContain("Every take has been reviewed");
    expect(html).toContain("Build the timeline");
    expect(html).toMatch(/href="\/timeline"/);
  });
});

describe("Reviewing a run in one decision", () => {
  it("offers to approve every pending take once there is more than one", () => {
    // A three-minute film is twenty-three takes. One at a time, review takes
    // longer than watching the film it is reviewing.
    const qc = queryClient();
    qc.setQueryData(
      ["takes", "project-1", null],
      [take({ id: "a" }), take({ id: "b" }), take({ id: "c" })],
    );

    const html = renderPage(qc);

    expect(html).toContain("Approve all 3 pending");
  });

  it("does not offer a batch for a single take", () => {
    // One click is already one click; a bulk control here is only clutter,
    // and a bulk control is exactly what should not be easy to hit by
    // accident.
    const qc = queryClient();
    qc.setQueryData(["takes", "project-1", null], [take({ id: "a" })]);

    expect(renderPage(qc)).not.toContain("Approve all");
  });

  it("counts only what the current filter is showing", () => {
    // The button acts on what is on screen, so it has to be named after that
    // - a count that includes takes the user filtered away is a promise to
    // act on takes they cannot see.
    const qc = queryClient();
    qc.setQueryData(
      ["takes", "project-1", null],
      [
        take({ id: "a" }),
        take({ id: "b" }),
        take({ id: "c", review_status: "Approved" }),
      ],
    );

    const html = renderPage(qc);

    expect(html).toContain("Approve all 2 pending");
  });
});
