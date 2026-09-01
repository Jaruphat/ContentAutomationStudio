/* ──────────────────────────────────────────────────────────────────────────
   AppLayout -- production cockpit 3-panel layout.
   LEFT:   Stage rail navigation (68px)
   CENTER: Main content area (Outlet)
   RIGHT:  Inspector panel (collapsible, 350px)
   ────────────────────────────────────────────────────────────────────────── */

import { Outlet } from "react-router-dom";
import StageRail from "./StageRail";
import Inspector from "./Inspector";

export default function AppLayout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-900">
      {/* LEFT rail */}
      <StageRail />

      {/* CENTER content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>

      {/* RIGHT inspector */}
      <Inspector />
    </div>
  );
}
