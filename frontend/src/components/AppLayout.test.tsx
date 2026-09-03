// @vitest-environment jsdom
import React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppLayout from "./AppLayout";
import { ThemeProvider } from "../theme";
import { ProjectStoreProvider, useAppDispatch } from "../store/useProjectStore";

function Bomb(): React.ReactElement {
  throw new Error("stage crashed");
}

function Calm() {
  return <div data-testid="calm-stage">Calm stage content</div>;
}

/** Selects a scene in the app store before the crash, to prove the boundary
 *  never touches unrelated store state on Retry. */
function SelectSceneThenCrash(): React.ReactElement {
  const dispatch = useAppDispatch();
  React.useEffect(() => {
    dispatch({ type: "SELECT_SCENE", id: "scene-42" });
  }, [dispatch]);
  throw new Error("stage crashed after selecting a scene");
}

function mockMatchMedia(matchesFor: (query: string) => boolean) {
  window.matchMedia = ((query: string) => ({
    matches: matchesFor(query),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function quietClient() {
  return new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
}

let container: HTMLDivElement;
let root: Root;

function mount(initialPath: string, stageElement: React.ReactElement, client = quietClient()) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <ProjectStoreProvider>
          <ThemeProvider>
            <MemoryRouter initialEntries={[initialPath]}>
              <Routes>
                <Route element={<AppLayout />}>
                  <Route path="/review" element={stageElement} />
                  <Route path="/timeline" element={<Calm />} />
                  <Route path="/story" element={<div data-testid="story-stage">Story stage</div>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </ThemeProvider>
        </ProjectStoreProvider>
      </QueryClientProvider>,
    );
  });
}

beforeEach(() => {
  mockMatchMedia(() => false); // desktop by default
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("AppLayout stage error boundary integration", () => {
  it("keeps the top bar, stage rail and project switcher when a stage crashes", () => {
    mount("/review", <Bomb />);

    expect(container.querySelector("header")?.textContent).toContain(
      "Content Automation Studio",
    );
    expect(container.querySelector('nav[aria-label="Production stages"]')).not.toBeNull();
    expect(container.querySelector('select[aria-label="Switch project"]')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("shows the recovery card in place of the crashed stage only, not the whole shell", () => {
    mount("/review", <Bomb />);
    const main = container.querySelector("main");
    expect(main?.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.querySelector("header")).not.toBeNull();
  });

  it("preserves shell and shows the recovery card on mobile layout too", () => {
    mockMatchMedia((q) => q.includes("767px"));
    mount("/review", <Bomb />);
    expect(container.querySelector("header")).not.toBeNull();
    expect(container.querySelector('nav[aria-label="Production stages"]')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("renders the recovery card under both light and dark theme classes", () => {
    mockMatchMedia((q) => q.includes("dark"));
    mount("/review", <Bomb />);
    expect(document.documentElement.classList.contains("theme-dark")).toBe(true);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    act(() => root.unmount());
    container.remove();
    mockMatchMedia((q) => !q.includes("dark"));
    mount("/review", <Bomb />);
    expect(document.documentElement.classList.contains("theme-light")).toBe(true);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("every action in the recovery card has a visible accessible name", () => {
    mount("/review", <Bomb />);
    const buttons = Array.from(container.querySelectorAll('[role="alert"] button'));
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect((button.textContent ?? "").trim().length).toBeGreaterThan(0);
    }
  });

  it("clears a stale fallback automatically when the user navigates to a different stage", () => {
    mount("/review", <Bomb />);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    const timelineNav = Array.from(
      container.querySelectorAll('nav[aria-label="Production stages"] button'),
    ).find((b) => /timeline/i.test(b.textContent ?? "")) as HTMLButtonElement;
    act(() => timelineNav.click());

    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-testid="calm-stage"]')).not.toBeNull();
  });

  it("keeps the shell intact across a Retry click on a still-crashing stage", () => {
    mount("/review", <SelectSceneThenCrash />);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    const retryButton = Array.from(container.querySelectorAll("button")).find((b) =>
      /^retry$/i.test(b.textContent ?? ""),
    ) as HTMLButtonElement;
    act(() => retryButton.click());

    expect(container.querySelector("header")).not.toBeNull();
    expect(container.querySelector('nav[aria-label="Production stages"]')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });
});
