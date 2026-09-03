// @vitest-environment jsdom
import { act } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SubtitleSettings } from "../types";
import SubtitleSettingsSection, {
  subtitlePresets,
  subtitlePreviewLayout,
  wrapSubtitlePreview,
} from "./SubtitleSettingsSection";

const apiMocks = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  exportSubtitles: vi.fn(),
  getProject: vi.fn(),
}));

vi.mock("../api/client", () => ({
  default: {
    subtitles: {
      get: apiMocks.getSettings,
      update: apiMocks.updateSettings,
      export: apiMocks.exportSubtitles,
    },
    projects: { get: apiMocks.getProject },
  },
  toAIError: (error: unknown) => ({
    detail: error instanceof Error ? error.message : "Unexpected error.",
    category: "unknown",
    provider_id: "",
  }),
}));

const settings = (overrides: Partial<SubtitleSettings> = {}): SubtitleSettings => ({
  mode: "soft",
  preset: "clean",
  font_family: "Segoe UI",
  font_size: 52,
  text_color: "#FFFFFF",
  outline_color: "#000000",
  shadow_color: "#000000",
  background_color: "#000000",
  bold: false,
  italic: false,
  outline_width: 3,
  shadow_depth: 2,
  background_box: false,
  position: "bottom",
  vertical_margin: 64,
  max_chars_per_line: 36,
  ...overrides,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

function renderSection(projectId: string) {
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <SubtitleSettingsSection projectId={projectId} />
      </QueryClientProvider>,
    );
  });
}

function button(label: string) {
  return [...container.querySelectorAll("button")].find((item) =>
    item.textContent?.includes(label),
  ) as HTMLButtonElement;
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function waitFor(predicate: () => boolean) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (predicate()) return;
    await flush();
  }
  expect(predicate()).toBe(true);
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  apiMocks.getProject.mockImplementation((id: string) =>
    Promise.resolve({ id, target_resolution: "1920x1080" }),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  client.clear();
  vi.clearAllMocks();
});

describe("subtitle project isolation", () => {
  it("resets the editor and gates Save until the newly selected project's GET succeeds", async () => {
    const first = deferred<SubtitleSettings>();
    const second = deferred<SubtitleSettings>();
    apiMocks.getSettings.mockImplementation((id: string) =>
      id === "project-a" ? first.promise : second.promise,
    );

    renderSection("project-a");
    expect(button("Save settings").disabled).toBe(true);

    await flush();
    await act(async () => first.resolve(settings({ font_size: 91 })));
    await flush();
    expect((container.querySelector('input[type="number"]') as HTMLInputElement).value).toBe("91");
    expect(button("Save settings").disabled).toBe(false);

    renderSection("project-b");
    expect(button("Save settings").disabled).toBe(true);
    expect((container.querySelector('select[aria-label="Subtitle mode"]') as HTMLSelectElement).value).toBe("off");

    await flush();
    await act(async () => second.resolve(settings({ font_size: 43 })));
    await flush();
    expect((container.querySelector('input[type="number"]') as HTMLInputElement).value).toBe("43");
    expect(button("Save settings").disabled).toBe(false);
  });

  it("ignores a late save response from the prior project", async () => {
    const saveA = deferred<SubtitleSettings>();
    apiMocks.getSettings.mockImplementation((id: string) =>
      Promise.resolve(settings({ font_size: id === "project-a" ? 61 : 47 })),
    );
    apiMocks.updateSettings.mockReturnValue(saveA.promise);

    renderSection("project-a");
    await waitFor(() => !button("Save settings").disabled);
    act(() => button("Save settings").click());
    await flush();
    expect(apiMocks.updateSettings).toHaveBeenCalledWith(
      "project-a",
      expect.objectContaining({ font_size: 61 }),
    );

    renderSection("project-b");
    await waitFor(() =>
      (container.querySelector('input[type="number"]') as HTMLInputElement).value === "47",
    );
    expect(button("Save settings").disabled).toBe(false);
    await act(async () => saveA.resolve(settings({ font_size: 99 })));

    expect((container.querySelector('input[type="number"]') as HTMLInputElement).value).toBe("47");
    expect(client.getQueryData<SubtitleSettings>(["subtitle-settings", "project-b"])?.font_size).toBe(47);
    expect(container.textContent).not.toContain("Subtitle settings saved.");
  });

  it("shows actionable GET, PUT, and download errors", async () => {
    apiMocks.getSettings.mockRejectedValueOnce(new Error("Project subtitles are unavailable"));
    renderSection("project-a");
    await flush();
    expect(container.textContent).toContain("Load subtitle settings failed.");
    expect(container.textContent).toContain("Project subtitles are unavailable");
    expect(button("Save settings").disabled).toBe(true);

    apiMocks.getSettings.mockResolvedValueOnce(settings());
    renderSection("project-b");
    await waitFor(() => !button("Save settings").disabled);
    apiMocks.updateSettings.mockRejectedValueOnce(new Error("Settings conflict; reload this project"));
    act(() => button("Save settings").click());
    await waitFor(() => container.textContent?.includes("Save subtitle settings failed.") ?? false);
    expect(container.textContent).toContain("Settings conflict; reload this project");

    apiMocks.exportSubtitles.mockRejectedValueOnce(new Error("No timed dialogue to export"));
    act(() => button("Export ASS").click());
    await waitFor(() => container.textContent?.includes("Download ASS subtitles failed.") ?? false);
    expect(container.textContent).toContain("No timed dialogue to export");
  });
});

describe("canonical subtitle presets", () => {
  it("defines every style field for every preset so prior selections cannot leak", () => {
    const styleKeys = [
      "font_family", "font_size", "text_color", "outline_color", "shadow_color",
      "background_color", "bold", "italic", "outline_width", "shadow_depth",
      "background_box", "position", "vertical_margin", "max_chars_per_line",
    ].sort();
    for (const preset of Object.values(subtitlePresets)) {
      expect(Object.keys(preset.values).sort()).toEqual(styleKeys);
    }
  });
});

describe("subtitle preview fidelity", () => {
  it("wraps preview copy at the configured limit and caps it at two lines", () => {
    expect(wrapSubtitlePreview("one two three four five six seven", 10)).toEqual([
      "one two", "three fou…",
    ]);
    expect(wrapSubtitlePreview("กิ".repeat(12), 8).join("\n")).not.toContain("ก\nิ");
  });

  it("scales font, outline, shadow, margin, and portrait cap from output resolution", () => {
    expect(subtitlePreviewLayout(settings({ font_size: 54, outline_width: 3, shadow_depth: 6, vertical_margin: 96 }), "1080x1920")).toEqual({
      aspectRatio: "9 / 16",
      fontSize: "5cqw",
      outlineWidth: "0.2778cqw",
      shadowDepth: "0.5556cqw",
      verticalMargin: "8.8889%",
      mobileMaxWidth: "247.5px",
    });
  });

  it("renders Off as off and uses a translucent background box when enabled", async () => {
    apiMocks.getSettings.mockResolvedValue(settings({ mode: "off", background_box: true }));
    renderSection("project-a");
    await flush();
    const preview = container.querySelector('[aria-label="Subtitle visual preview"]')!;
    expect(preview.textContent).toContain("Subtitles off");
    expect(preview.textContent).not.toContain("Beautiful captions");

    apiMocks.getSettings.mockResolvedValue(settings({ mode: "soft", background_box: true }));
    renderSection("project-b");
    await flush();
    const cue = container.querySelector('[data-testid="subtitle-preview-cue"]') as HTMLElement;
    expect(cue.style.backgroundColor).toContain("87.5%");
  });
});
