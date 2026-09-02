import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProjectSwitcher from "../components/ProjectSwitcher";
import { ProjectStoreProvider } from "../store/useProjectStore";
import {
  NEW_PROJECT_DEFAULTS,
  NEW_PROJECT_TEMPLATES,
  newProjectTemplate,
  persistProject,
  shouldLoadProjectIntoForm,
} from "./StoryPage";

function renderSwitcher() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { enabled: false } },
  });
  queryClient.setQueryData(["projects"], [
    { id: "existing", title: "Existing project" },
    { id: "second", title: "Second project" },
  ]);
  return renderToStaticMarkup(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ProjectStoreProvider>
          <ProjectSwitcher />
        </ProjectStoreProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("project switch and new-project flow", () => {
  it("keeps Switch and New controls visible when projects already exist", () => {
    const html = renderSwitcher();
    expect(html).toContain('aria-label="Switch project"');
    expect(html).toContain("Existing project");
    expect(html).toContain("Second project");
    expect(html).toContain("New");
    for (const label of ["Blank", "Start from Plot", "YouTube", "Shorts", "Story Video"]) {
      expect(html).toContain(label);
    }
  });

  it("defines clean defaults rather than reusing a selected project", () => {
    expect(NEW_PROJECT_DEFAULTS).toEqual({
      title: "",
      objective: "",
      audience: "",
      contentType: "video",
      aspectRatio: "16:9",
      duration: "180",
      language: "en",
      plot: "",
    });
  });

  it("ignores an old selected-project response that resolves after New starts", async () => {
    let resolveOldProject!: (project: { id: string; title: string }) => void;
    const oldProjectRequest = new Promise<{ id: string; title: string }>((resolve) => {
      resolveOldProject = resolve;
    });

    // The request began while this project was selected.
    let currentProjectId: string | null = "old-project";
    let creatingProject = false;

    // New enters draft mode before the old request resolves.
    currentProjectId = null;
    creatingProject = true;
    resolveOldProject({ id: "old-project", title: "The Lost Garden" });
    const staleProject = await oldProjectRequest;

    expect(
      shouldLoadProjectIntoForm(staleProject, currentProjectId, creatingProject),
    ).toBe(false);
  });

  it("creates with POST semantics in draft mode even if an old id is still captured", async () => {
    const created = { id: "new-project", title: "Unique regression project" };
    const create = vi.fn().mockResolvedValue(created);
    const update = vi.fn().mockResolvedValue({ id: "old-project" });
    const payload = { ...NEW_PROJECT_DEFAULTS, title: created.title };

    const result = await persistProject(
      {
        creatingProject: true,
        currentProjectId: "old-project",
        payload: {
          title: payload.title,
          objective: payload.objective,
          audience: payload.audience,
          content_type: payload.contentType,
          aspect_ratio: payload.aspectRatio,
          target_duration_sec: Number(payload.duration),
          language: payload.language,
          plot_text: payload.plot,
        },
      },
      { create, update },
    );

    expect(result).toBe(created);
    expect(create).toHaveBeenCalledOnce();
    expect(update).not.toHaveBeenCalled();
  });

  it("updates only when editing a selected existing project", async () => {
    const create = vi.fn();
    const update = vi.fn().mockResolvedValue({ id: "existing" });
    const payload = {
      title: "Existing project",
      objective: "unchanged",
      audience: "",
      content_type: "video",
      aspect_ratio: "16:9",
      target_duration_sec: 180,
      language: "en",
      plot_text: "",
    };

    await persistProject(
      { creatingProject: false, currentProjectId: "existing", payload },
      { create, update },
    );

    expect(update).toHaveBeenCalledWith("existing", payload);
    expect(create).not.toHaveBeenCalled();
  });

  it("offers blank, plot, and requested content-brief templates", () => {
    expect(NEW_PROJECT_TEMPLATES.map((item) => item.label)).toEqual([
      "Blank",
      "Start from Plot",
      "YouTube",
      "Shorts",
      "Story Video",
    ]);
    expect(newProjectTemplate("youtube")).toMatchObject({
      title: "Untitled YouTube Video",
      aspectRatio: "16:9",
      duration: "480",
    });
    expect(newProjectTemplate("shorts")).toMatchObject({
      title: "Untitled Short",
      aspectRatio: "9:16",
      duration: "45",
    });
    expect(newProjectTemplate("story").title).toBe("Untitled Story Video");
  });
});
