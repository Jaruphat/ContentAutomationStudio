/* ──────────────────────────────────────────────────────────────────────────
   AppLayout -- production cockpit shell.

   The shell has three responsive shapes, and this component owns the two
   breakpoints that pick between them so StageRail and Inspector stay dumb:

   * >= 1024px  rail + centre + docked inspector (the desktop cockpit).
   * 768-1023px rail + centre, inspector becomes an overlay drawer opened from
     the rail -- a 350px panel plus an 88px rail leaves too little centre.
   * < 768px    top bar + centre + bottom stage bar, inspector still a drawer.
   ────────────────────────────────────────────────────────────────────────── */

import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { PanelRight } from "lucide-react";
import StageRail, { ThemeControl } from "./StageRail";
import Inspector from "./Inspector";
import { useAppState, useAppDispatch } from "../store/useProjectStore";

/** Subscribes to a media query so layout changes follow a live resize. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(
    () => window.matchMedia?.(query).matches ?? false,
  );

  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    setMatches(media.matches);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

function TopBar() {
  const { inspectorOpen } = useAppState();
  const dispatch = useAppDispatch();

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-2">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">
        CA
      </div>
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-zinc-100">
        Content Automation Studio
      </h1>
      <ThemeControl compact />
      <button
        type="button"
        data-inspector-toggle
        onClick={() => dispatch({ type: "TOGGLE_INSPECTOR" })}
        aria-expanded={inspectorOpen}
        title="Inspector"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
      >
        <PanelRight size={18} strokeWidth={1.7} />
        <span className="sr-only">Inspector</span>
      </button>
    </header>
  );
}

export default function AppLayout() {
  const compactNav = useMediaQuery("(max-width: 767px)");
  const drawerInspector = useMediaQuery("(max-width: 1023px)");
  const dispatch = useAppDispatch();

  // Shrinking past the docked breakpoint closes the inspector: as a drawer it
  // would otherwise cover the centre panel the moment the layout switches.
  // Growing back does not re-open it, so a deliberate collapse survives a
  // resize; the rail toggle brings it back.
  useEffect(() => {
    if (drawerInspector) dispatch({ type: "SET_INSPECTOR", open: false });
  }, [drawerInspector, dispatch]);

  if (compactNav) {
    return (
      // dvh rather than vh so the bottom stage bar is not hidden behind mobile
      // browser chrome.
      <div className="flex h-dvh w-full flex-col overflow-hidden bg-zinc-900">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
        <StageRail variant="bar" />
        <Inspector variant="drawer" />
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-900">
      <StageRail variant="rail" showInspectorToggle={drawerInspector} />

      {/* min-w-0 so a wide child (a table, a long prompt) scrolls inside the
          centre panel instead of pushing the rail and inspector off-screen. */}
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>

      <Inspector variant={drawerInspector ? "drawer" : "docked"} />
    </div>
  );
}
