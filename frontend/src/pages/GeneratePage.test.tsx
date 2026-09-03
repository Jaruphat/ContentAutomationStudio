import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import GeneratePage from "./GeneratePage";

vi.mock("../store/useProjectStore", () => ({
  useAppState: () => ({ currentProjectId: "project-1", queuePaused: false }),
  useAppDispatch: () => vi.fn(),
}));

function queryClient() {
  return new QueryClient({
    defaultOptions: { queries: { enabled: false, retry: false } },
  });
}

function renderPage(qc: QueryClient, path = "/generate") {
  if (
    !qc.getQueryCache().find({
      queryKey: ["selected-project", "project-1"],
      exact: true,
    })
  ) {
    qc.setQueryData(["selected-project", "project-1"], {
      id: "project-1",
      title: "Project",
    });
  }
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <GeneratePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function job(overrides: Record<string, unknown>) {
  return {
    id: "job-1",
    shot_id: "shot-12345678",
    workflow_id: null,
    workflow_version: "1",
    workflow_snapshot_path: null,
    workflow_sha256: null,
    parameter_map: {},
    media_provider_id: "comfyui",
    media_model: "workflow-v1",
    request_params: null,
    usage: null,
    estimated_cost_usd: null,
    provenance: null,
    seed: 42,
    comfyui_prompt_id: null,
    status: "Completed",
    attempts: 1,
    error_code: null,
    error_message: null,
    outputs: [],
    submitted_at: null,
    started_at: null,
    completed_at: null,
    created_at: "2026-09-02T00:00:00Z",
    ...overrides,
  };
}

describe("Generate runtime truthfulness", () => {
  it("offers valid API image and video defaults for the missing-workflow blocker", () => {
    const qc = queryClient();
    qc.setQueryData(["preflight", "project-1"], {
      ready: false,
      total_shots: 1,
      ready_shots: 0,
      issues: [
        {
          shot_id: "shot-1",
          scene_id: "scene-1",
          shot_order: 1,
          issues: ["No workflow assigned (shot or project default)"],
        },
      ],
      workflow_checks: [],
      warnings: [],
      comfyui_online: true,
      comfyui_mock: false,
    });
    qc.setQueryData(["workflows"], [
      {
        id: "image-general",
        name: "General image API",
        purpose: "image",
        source_format: "api",
        validation_status: "valid",
        parameter_mapping: { positivePrompt: { nodeId: "1", field: "text" } },
      },
      {
        id: "image-reference-edit",
        name: "Reference image edit API",
        purpose: "image",
        source_format: "api",
        validation_status: "valid",
        parameter_mapping: { referenceImage: { nodeId: "2", field: "image" } },
      },
      {
        id: "video-api",
        name: "H3 image to video API",
        purpose: "image-to-video",
        source_format: "api",
        validation_status: "valid",
        parameter_mapping: {},
      },
      {
        id: "video-ui",
        name: "Invalid UI video workflow",
        purpose: "text-to-video",
        source_format: "ui",
        validation_status: "valid",
        parameter_mapping: {},
      },
      {
        id: "image-pending",
        name: "Pending API image workflow",
        purpose: "image",
        source_format: "api",
        validation_status: "pending",
        parameter_mapping: {},
      },
    ]);

    const html = renderPage(qc);

    expect(html).toContain("Default image workflow");
    expect(html).toContain("Default video workflow");
    expect(html).toContain("Apply workflows");
    expect(html).toContain("General image API");
    expect(html).toContain("H3 image to video API");
    expect(html).not.toContain("Reference image edit API");
    expect(html).not.toContain("Invalid UI video workflow");
    expect(html).not.toContain("Pending API image workflow");
  });

  it("hides workflow recovery controls without the missing-workflow blocker", () => {
    const qc = queryClient();
    qc.setQueryData(["preflight", "project-1"], {
      ready: false,
      total_shots: 1,
      ready_shots: 0,
      issues: [
        {
          shot_id: "shot-1",
          scene_id: "scene-1",
          shot_order: 1,
          issues: ["Shot status is 'NeedsReview'"],
        },
      ],
      workflow_checks: [],
      warnings: [],
      comfyui_online: true,
      comfyui_mock: false,
    });

    const html = renderPage(qc);

    expect(html).not.toContain("Default image workflow");
    expect(html).not.toContain("Default video workflow");
    expect(html).not.toContain("Apply workflows");
  });

  it("prominently identifies live ComfyUI mock health as simulation", () => {
    const qc = queryClient();
    qc.setQueryData(["project", "project-1"], { id: "project-1", title: "Project" });
    qc.setQueryData(["media-health"], {
      providers: [
        {
          id: "comfyui",
          configured: true,
          online: true,
          mock: true,
          model: "mock",
          error: "",
        },
      ],
    });

    const html = renderPage(qc);

    expect(html).toContain("SIMULATION · Mock");
    expect(html).not.toContain("REAL · ComfyUI connected");
  });

  it("identifies a live non-mock ComfyUI health response as real", () => {
    const qc = queryClient();
    qc.setQueryData(["media-health"], {
      providers: [
        {
          id: "comfyui",
          configured: true,
          online: true,
          mock: false,
          model: "comfyui",
          error: "",
        },
      ],
    });

    const html = renderPage(qc);

    expect(html).toContain("REAL · ComfyUI connected");
    expect(html).not.toContain("SIMULATION · Mock");
  });

  it("does not imply a real connection when ComfyUI health is offline", () => {
    const qc = queryClient();
    qc.setQueryData(["media-health"], {
      providers: [
        {
          id: "comfyui",
          configured: true,
          online: false,
          mock: false,
          model: "comfyui",
          error: "connection refused",
        },
      ],
    });

    const html = renderPage(qc);

    expect(html).toContain("OFFLINE · ComfyUI unavailable");
    expect(html).not.toContain("REAL · ComfyUI connected");
  });

  it("blocks a planned ComfyUI run in mock mode pending explicit acknowledgement", () => {
    const qc = queryClient();
    qc.setQueryData(["project", "project-1"], { id: "project-1", title: "Project" });
    qc.setQueryData(["media-health"], {
      providers: [
        {
          id: "comfyui",
          configured: true,
          online: true,
          mock: true,
          model: "mock",
          error: "",
        },
      ],
    });
    qc.setQueryData(["generation-estimate", "project-1"], {
      shot_count: 1,
      paid_shot_count: 0,
      requires_confirmation: false,
      estimated_cost_usd: null,
      unpriced_paid_shots: 0,
      providers: [
        {
          provider_id: "comfyui",
          model: "workflow-v1",
          shot_count: 1,
          paid: false,
          configured: true,
          estimated_cost_usd: null,
          cost_basis: "",
        },
      ],
      shots: [
        {
          shot_id: "shot-1",
          generation_mode: "image",
          provider_id: "comfyui",
          model: "workflow-v1",
          workflow_id: "workflow-1",
          estimated_cost_usd: null,
          cost_basis: "",
          paid: false,
          blockers: [],
        },
      ],
      blockers: [],
    });

    const html = renderPage(qc);

    expect(html).toContain("I intend to generate placeholder media in Simulation Mode");
    expect(html).toMatch(/<button disabled=""[^>]*>[\s\S]*?Generate<\/button>/);
  });

  it("blocks a ComfyUI run while live runtime health is unavailable", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-estimate", "project-1"], {
      shot_count: 1,
      paid_shot_count: 0,
      requires_confirmation: false,
      estimated_cost_usd: null,
      unpriced_paid_shots: 0,
      providers: [],
      shots: [
        {
          shot_id: "shot-1",
          generation_mode: "image",
          provider_id: "comfyui",
          model: "workflow-v1",
          workflow_id: "workflow-1",
          estimated_cost_usd: null,
          cost_basis: "",
          paid: false,
          blockers: [],
        },
      ],
      blockers: [],
    });

    const html = renderPage(qc);

    expect(html).toContain("Live ComfyUI runtime is not available");
    expect(html).toMatch(/<button disabled=""[^>]*>[\s\S]*?Generate<\/button>/);
  });

  it("keeps Generate disabled when project preflight is not ready", () => {
    const qc = queryClient();
    qc.setQueryData(["media-health"], {
      providers: [
        {
          id: "comfyui",
          configured: true,
          online: true,
          mock: false,
          model: "comfyui",
          error: "",
        },
      ],
    });
    qc.setQueryData(["preflight", "project-1"], {
      ready: false,
      total_shots: 1,
      ready_shots: 0,
      issues: [
        {
          shot_id: "shot-1",
          scene_id: "scene-1",
          shot_order: 1,
          issues: ["Shot status is 'NeedsReview'"],
        },
      ],
      workflow_checks: [],
      warnings: [],
      comfyui_online: true,
      comfyui_mock: false,
    });
    qc.setQueryData(["generation-estimate", "project-1"], {
      shot_count: 1,
      paid_shot_count: 0,
      requires_confirmation: false,
      estimated_cost_usd: null,
      unpriced_paid_shots: 0,
      providers: [],
      shots: [],
      blockers: [],
    });

    const html = renderPage(qc);

    expect(html).toMatch(
      /<button(?=[^>]*data-testid="generate-button")(?=[^>]*disabled="")[^>]*>/,
    );
  });

  it("shows provider-specific runtime evidence for every job", () => {
    const qc = queryClient();
    qc.setQueryData(["project", "project-1"], { id: "project-1", title: "Project" });
    qc.setQueryData(["media-providers"], {
      default_image_provider_id: "comfyui",
      video_provider_id: "comfyui",
      providers: [
        { id: "comfyui", label: "Local ComfyUI" },
        { id: "openai", label: "OpenAI Images" },
      ],
    });
    qc.setQueryData(["jobs", "project-1"], [
      job({ id: "mock-job", comfyui_prompt_id: "mock-mock-job" }),
      job({ id: "real-job", comfyui_prompt_id: "prompt-real-123" }),
      job({
        id: "openai-job",
        media_provider_id: "openai",
        media_model: "gpt-image-1",
        comfyui_prompt_id: null,
      }),
    ]);

    const html = renderPage(qc);

    expect(html).toContain("SIMULATION · Mock");
    expect(html).toContain("ComfyUI prompt prompt-real-123");
    expect(html).toContain("OpenAI Images · gpt-image-1");
  });

  it("derives paused state from the backend queue status", () => {
    const qc = queryClient();
    qc.setQueryData(["queue-status", "project-1"], {
      paused: true,
      total_jobs: 13,
      queued: 3,
      running: 0,
      completed: 10,
      failed: 0,
    });
    qc.setQueryData(["jobs", "project-1"], [job({ status: "Queued" })]);

    const html = renderPage(qc);

    expect(html).toContain("Resume queue");
    expect(html).not.toContain("Pause queue");
  });

  it("polls jobs preflight and estimate while project jobs exist", () => {
    const qc = queryClient();
    qc.setQueryData(["jobs", "project-1"], [job({ status: "Completed" })]);

    renderPage(qc);

    for (const queryKey of [
      ["jobs", "project-1"],
      ["preflight", "project-1"],
      ["generation-estimate", "project-1"],
    ]) {
      const query = qc.getQueryCache().find({ queryKey, exact: true });
      const options = query?.options as
        | { refetchInterval?: unknown }
        | undefined;
      expect(options?.refetchInterval).toBe(2000);
    }
  });

  it("shows the backend completed running queued and paused summary", () => {
    const qc = queryClient();
    qc.setQueryData(["queue-status", "project-1"], {
      paused: true,
      total_jobs: 13,
      queued: 3,
      running: 0,
      completed: 10,
      failed: 0,
    });
    qc.setQueryData(["jobs", "project-1"], [job({ status: "Completed" })]);

    const html = renderPage(qc);

    expect(html).toContain("Total: <span class=\"text-zinc-300\">13</span>");
    expect(html).toContain("Queued: 3");
    expect(html).toContain("Running: 0");
    expect(html).toContain("Completed: 10");
    expect(html).toContain("Paused");
  });

  it("hides queue controls when no jobs are queued or running", () => {
    const qc = queryClient();
    qc.setQueryData(["queue-status", "project-1"], {
      paused: true,
      total_jobs: 13,
      queued: 0,
      running: 0,
      completed: 13,
      failed: 0,
    });
    qc.setQueryData(["jobs", "project-1"], [job({ status: "Completed" })]);

    const html = renderPage(qc);

    expect(html).not.toContain("Pause queue");
    expect(html).not.toContain("Resume queue");
  });

  it("hides a stale project's cached queue and offers a safe project switch", () => {
    const qc = queryClient();
    qc.setQueryData(["selected-project", "project-1"], {
      id: "project-1",
      title: "Deleted project",
    });
    const projectQuery = qc.getQueryCache().find({
      queryKey: ["selected-project", "project-1"],
      exact: true,
    })!;
    projectQuery.setState({
      ...projectQuery.state,
      status: "error",
      fetchStatus: "idle",
      error: new Error("Project not found"),
    });
    qc.setQueryData(["jobs", "project-1"], [
      job({ id: "cached-job", comfyui_prompt_id: "mock-cached-job" }),
    ]);

    const html = renderPage(qc);

    expect(html).toContain("Project unavailable");
    expect(html).toContain("Switch project");
    expect(html).not.toContain("mock-cached-job");
    expect(html).not.toContain("Job Queue");
  });
});

// ── Generation runs ───────────────────────────────────────────────────────

function runJob(overrides: Record<string, unknown> = {}) {
  return {
    job_id: "job-1",
    run_id: "run-1",
    shot_id: "shot-12345678",
    scene_id: "scene-1",
    scene_name: "Opening Scene",
    shot_name: "Shot 1 - Alice",
    status: "Completed",
    attempts: 1,
    error_message: null,
    media_provider_id: "comfyui",
    media_model: "workflow-v1",
    seed: 42,
    created_at: "2026-09-03T00:00:00Z",
    completed_at: "2026-09-03T00:01:00Z",
    take_id: "take-1",
    take_review_status: "Pending",
    thumbnail_url: "/api/media/takes/take-1/file",
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
    total_jobs: 1,
    queued: 0,
    running: 0,
    completed: 1,
    failed: 0,
    cancelled: 0,
    pending_take_count: 1,
    ready_for_review: true,
    created_at: "2026-09-03T00:00:00Z",
    jobs: [runJob()],
    ...overrides,
  };
}

describe("Generate run batches", () => {
  it("names the scene and shot of each job instead of showing only ids", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run-current", "project-1"], run());

    const html = renderPage(qc);

    expect(html).toContain("Run 3");
    expect(html).toContain("Opening Scene");
    expect(html).toContain("Shot 1 - Alice");
  });

  it("shows the take preview a completed job produced", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run-current", "project-1"], run());

    const html = renderPage(qc);

    expect(html).toContain('src="/api/media/takes/take-1/file"');
  });

  it("draws a placeholder when a job has no servable preview", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({ jobs: [runJob({ thumbnail_url: null, take_id: null })] }),
    );

    const html = renderPage(qc);

    expect(html).toContain("No preview");
    expect(html).not.toContain("/api/media/takes/");
  });

  it("reports counts scoped to the current run", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({
        total_jobs: 5,
        completed: 3,
        failed: 1,
        queued: 1,
        terminal: false,
        status: "Queued",
      }),
    );

    const html = renderPage(qc);

    expect(html).toContain("3 completed");
    expect(html).toContain("1 failed");
    expect(html).toContain("1 queued");
    expect(html).toContain("of 5");
  });

  it("includes cancelled jobs in run and queue totals", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({ total_jobs: 2, completed: 1, cancelled: 1 }),
    );
    qc.setQueryData(["queue-status", "project-1"], {
      paused: false,
      total_jobs: 2,
      queued: 0,
      running: 0,
      completed: 1,
      failed: 0,
      cancelled: 1,
    });

    const html = renderPage(qc);

    expect(html).toContain("1 cancelled");
    expect(html).toContain("Cancelled: 1");
  });

  it("offers an obvious Go to Review once the run is finished with takes waiting", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run-current", "project-1"], run());

    const html = renderPage(qc);

    expect(html).toContain("Go to Review");
    expect(html).toMatch(/href="\/review\?run=run-1"/);
  });

  it("does not send the user to Review while the run is still generating", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({ terminal: false, status: "Running", running: 1, ready_for_review: false }),
    );

    const html = renderPage(qc);

    expect(html).not.toContain("Go to Review");
  });

  it("does not send the user to Review when the run produced nothing to review", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({
        status: "Failed",
        completed: 0,
        failed: 1,
        pending_take_count: 0,
        ready_for_review: false,
        jobs: [
          runJob({
            status: "Failed",
            take_id: null,
            thumbnail_url: null,
            error_message: "out of memory",
          }),
        ],
      }),
    );

    const html = renderPage(qc);

    expect(html).not.toContain("Go to Review");
  });

  it("links the four queue views as tabs", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run-current", "project-1"], run());

    const html = renderPage(qc);

    expect(html).toMatch(/href="\/generate\?tab=failed"/);
    expect(html).toMatch(/href="\/generate\?tab=completed"/);
    expect(html).toMatch(/href="\/generate\?tab=history"/);
    expect(html).toContain("Current");
    expect(html).toMatch(/aria-current="page"[^>]*>Current<\/a>/);
  });

  it("shows only the failed jobs of the current run on the Failed tab", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({
        jobs: [
          runJob({ job_id: "ok-job", shot_name: "Shot 1 - Alice" }),
          runJob({
            job_id: "bad-job",
            shot_name: "Shot 2 - Bob",
            status: "Failed",
            take_id: null,
            thumbnail_url: null,
            error_message: "CUDA out of memory",
          }),
        ],
      }),
    );

    const html = renderPage(qc, "/generate?tab=failed");

    expect(html).toContain("Shot 2 - Bob");
    expect(html).toContain("CUDA out of memory");
    expect(html).not.toContain("Shot 1 - Alice");
  });

  it("shows only the completed jobs of the current run on the Completed tab", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-run-current", "project-1"],
      run({
        jobs: [
          runJob({ job_id: "ok-job", shot_name: "Shot 1 - Alice" }),
          runJob({
            job_id: "bad-job",
            shot_name: "Shot 2 - Bob",
            status: "Failed",
            take_id: null,
            thumbnail_url: null,
          }),
        ],
      }),
    );

    const html = renderPage(qc, "/generate?tab=completed");

    expect(html).toContain("Shot 1 - Alice");
    expect(html).not.toContain("Shot 2 - Bob");
  });

  it("groups every past run under its own heading on the History tab", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-runs", "project-1", 51], [
      run({
        id: "run-2",
        label: "Run 4 (regenerate)",
        kind: "regeneration",
        sequence: 4,
        jobs: [runJob({ job_id: "j4", run_id: "run-2", shot_name: "Shot 9 - Cleo" })],
      }),
      run({
        jobs: [runJob({ job_id: "j3", shot_name: "Shot 1 - Alice" })],
      }),
    ]);

    const html = renderPage(qc, "/generate?tab=history");

    expect(html).toContain("Run 4 (regenerate)");
    expect(html).toContain("Run 3");
    expect(html).toContain("Shot 9 - Cleo");
    expect(html).toContain("Shot 1 - Alice");
  });

  it("polls run history and explicitly offers more than the first 50", () => {
    const qc = queryClient();
    qc.setQueryData(
      ["generation-runs", "project-1", 51],
      Array.from({ length: 51 }, (_, index) =>
        run({ id: `run-${index}`, label: `Run ${index + 1}` }),
      ),
    );

    const html = renderPage(qc, "/generate?tab=history");
    const query = qc.getQueryCache().find({
      queryKey: ["generation-runs", "project-1", 51],
      exact: true,
    });

    expect(query).toBeDefined();
    expect((query!.options as { refetchInterval?: unknown }).refetchInterval).toBe(2000);
    expect(html).toContain("Load 50 more runs");
    expect(html).not.toContain("Run 51</h3>");
  });

  it("shows history request errors instead of a loading message", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-runs", "project-1", 51], []);
    const query = qc.getQueryCache().find({
      queryKey: ["generation-runs", "project-1", 51],
      exact: true,
    })!;
    query.setState({
      ...query.state,
      status: "error",
      fetchStatus: "idle",
      error: new Error("History unavailable"),
    });

    const html = renderPage(qc, "/generate?tab=history");

    expect(html).toContain("History unavailable");
    expect(html).not.toContain("Loading run history");
  });

  it("says so plainly when nothing has been generated yet", () => {
    const qc = queryClient();
    qc.setQueryData(["generation-run-current", "project-1"], null);
    qc.setQueryData(["jobs", "project-1"], []);

    const html = renderPage(qc);

    expect(html).toContain("No generation jobs yet");
  });
});
