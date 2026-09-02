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

function renderPage(qc: QueryClient) {
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
    <MemoryRouter>
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
