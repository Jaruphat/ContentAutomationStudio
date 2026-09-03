// @vitest-environment jsdom
import React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StageErrorBoundary from "./StageErrorBoundary";
import { ProjectStoreProvider, useAppDispatch, useAppState } from "../store/useProjectStore";

const navigateSpy = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateSpy };
});

/** Throws exactly once per mount so a remount can succeed. */
function Bomb({ message = "Cannot read properties of undefined" }: { message?: string }): React.ReactElement {
  throw new Error(message);
}

function Calm() {
  return <div data-testid="calm-stage">All good</div>;
}

let container: HTMLDivElement;
let root: Root;

function mount(ui: React.ReactElement, path = "/review") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
  });
}

function withClient(child: React.ReactElement, client = new QueryClient()) {
  return <QueryClientProvider client={client}>{child}</QueryClientProvider>;
}

beforeEach(() => {
  navigateSpy.mockClear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("StageErrorBoundary", () => {
  it("renders children normally when nothing throws", () => {
    mount(withClient(<StageErrorBoundary><Calm /></StageErrorBoundary>));
    expect(container.querySelector('[data-testid="calm-stage"]')).not.toBeNull();
  });

  it("replaces only the crashed content with an alert recovery card", () => {
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent).toMatch(/went wrong|problem/i);
  });

  it("offers Reload data, Retry, Back to Projects and Copy diagnostic ID actions", () => {
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const buttons = Array.from(container.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons.some((t) => /reload data/i.test(t ?? ""))).toBe(true);
    expect(buttons.some((t) => /^retry$/i.test(t ?? ""))).toBe(true);
    expect(buttons.some((t) => /back to projects/i.test(t ?? ""))).toBe(true);
    expect(buttons.some((t) => /copy diagnostic id/i.test(t ?? ""))).toBe(true);
  });

  it("keeps technical details collapsed by default", () => {
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details?.hasAttribute("open")).toBe(false);
  });

  it("never exposes the raw file path from the error inside technical details", () => {
    mount(
      withClient(
        <StageErrorBoundary>
          <Bomb message={String.raw`boom at C:\Users\jongp\Desktop\secretproj\Page.tsx:12:3`} />
        </StageErrorBoundary>,
      ),
    );
    const details = container.querySelector("details");
    expect(details?.textContent).not.toContain("jongp");
    expect(details?.textContent).not.toMatch(/[A-Za-z]:\\/);
  });

  it("shows a stable-looking diagnostic id inside technical details", () => {
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const details = container.querySelector("details");
    expect(details?.textContent).toMatch(/ERR-[0-9A-F]{8}/);
  });

  it("logs a sanitized diagnostic to console.error, never the raw path", () => {
    mount(
      withClient(
        <StageErrorBoundary>
          <Bomb message={String.raw`boom at C:\Users\jongp\Desktop\secretproj\Page.tsx:12:3`} />
        </StageErrorBoundary>,
      ),
    );
    const errorSpy = console.error as unknown as ReturnType<typeof vi.fn>;
    const loggedPayloads = errorSpy.mock.calls.flat().map((v) => JSON.stringify(v));
    const anyPath = loggedPayloads.some((s) => s.includes("jongp"));
    expect(anyPath).toBe(false);
    const anyDiagnosticId = loggedPayloads.some((s) => /ERR-[0-9A-F]{8}/.test(s));
    expect(anyDiagnosticId).toBe(true);
  });

  it("Retry remounts the stage and clears the fallback once the child stops throwing", () => {
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("transient");
      return <div data-testid="recovered">Recovered</div>;
    }

    mount(withClient(<StageErrorBoundary><Flaky /></StageErrorBoundary>));
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    shouldThrow = false;
    const retryButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /^retry$/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => retryButton.click());

    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-testid="recovered"]')).not.toBeNull();
  });

  it("Reload data resets only query keys relevant to the current stage", () => {
    const client = new QueryClient();
    client.setQueryData(["timeline", "project-1"], { items: [] });
    client.setQueryData(["takes", "project-1"], []);
    const resetSpy = vi.spyOn(client, "resetQueries");

    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>, client), "/timeline");

    const reloadButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /reload data/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => reloadButton.click());

    expect(resetSpy).toHaveBeenCalled();
    const predicate = resetSpy.mock.calls[0][0]?.predicate as
      | ((query: { queryKey: unknown[] }) => boolean)
      | undefined;
    expect(predicate?.({ queryKey: ["timeline", "project-1"] })).toBe(true);
    expect(predicate?.({ queryKey: ["takes", "project-1"] })).toBe(false);
  });

  it("Reload data also clears the fallback so the stage remounts", () => {
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("transient");
      return <div data-testid="recovered">Recovered</div>;
    }
    mount(withClient(<StageErrorBoundary><Flaky /></StageErrorBoundary>), "/timeline");
    shouldThrow = false;
    const reloadButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /reload data/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => reloadButton.click());
    expect(container.querySelector('[data-testid="recovered"]')).not.toBeNull();
  });

  it("Back to Projects navigates to /story and dismisses the fallback", () => {
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const backButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /back to projects/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => backButton.click());
    expect(navigateSpy).toHaveBeenCalledWith("/story");
  });

  it("Copy diagnostic ID writes the id to the clipboard without crashing", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const details = container.querySelector("details");
    const idMatch = details?.textContent?.match(/ERR-[0-9A-F]{8}/);
    expect(idMatch).not.toBeNull();

    const copyButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /copy diagnostic id/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    await act(async () => {
      copyButton.click();
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledWith(idMatch?.[0]);
  });

  it("Copy diagnostic ID does not throw when clipboard is unavailable", async () => {
    Object.assign(navigator, { clipboard: undefined });
    mount(withClient(<StageErrorBoundary><Bomb /></StageErrorBoundary>));
    const copyButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /copy diagnostic id/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    await act(async () => {
      copyButton.click();
      await Promise.resolve();
    });
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("does not touch unrelated app-store state -- selected scene survives a crash and Retry", () => {
    function Selector() {
      const dispatch = useAppDispatch();
      React.useEffect(() => {
        dispatch({ type: "SELECT_SCENE", id: "scene-42" });
      }, [dispatch]);
      return null;
    }

    function Probe() {
      const { selectedSceneId } = useAppState();
      return <div data-testid="selected-scene">{selectedSceneId ?? "none"}</div>;
    }

    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("boom");
      return <div data-testid="recovered">recovered</div>;
    }

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/review"]}>
          <QueryClientProvider client={new QueryClient()}>
            <ProjectStoreProvider>
              <Probe />
              <Selector />
              <StageErrorBoundary>
                <Flaky />
              </StageErrorBoundary>
            </ProjectStoreProvider>
          </QueryClientProvider>
        </MemoryRouter>,
      );
    });

    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="selected-scene"]')?.textContent).toBe(
      "scene-42",
    );

    shouldThrow = false;
    const retryButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /^retry$/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => retryButton.click());

    expect(container.querySelector('[data-testid="recovered"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="selected-scene"]')?.textContent).toBe(
      "scene-42",
    );
  });
});
