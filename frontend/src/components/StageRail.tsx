/* ──────────────────────────────────────────────────────────────────────────
   StageRail -- vertical left-side navigation rail with production stages.
   Each stage maps to a route; the active stage is highlighted.
   ────────────────────────────────────────────────────────────────────────── */

import { useLocation, useNavigate } from "react-router-dom";
import {
  BookOpen,
  LayoutGrid,
  Zap,
  CheckCircle,
  Film,
  Download,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Stage {
  label: string;
  path: string;
  icon: LucideIcon;
}

const stages: Stage[] = [
  { label: "Story", path: "/story", icon: BookOpen },
  { label: "Storyboard", path: "/storyboard", icon: LayoutGrid },
  { label: "Generate", path: "/generate", icon: Zap },
  { label: "Review", path: "/review", icon: CheckCircle },
  { label: "Timeline", path: "/timeline", icon: Film },
  { label: "Export", path: "/export", icon: Download },
];

export default function StageRail() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav className="flex h-full w-[68px] flex-col items-center bg-zinc-950 py-4 panel-border-r select-none">
      <div className="mb-6 flex h-8 w-8 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">
        CA
      </div>

      <div className="flex flex-1 flex-col gap-1">
        {stages.map((s) => {
          const active = location.pathname.startsWith(s.path);
          const Icon = s.icon;

          return (
            <button
              key={s.path}
              onClick={() => navigate(s.path)}
              title={s.label}
              className={`group flex w-14 flex-col items-center gap-1 rounded-lg px-1 py-2 text-[10px] leading-tight transition-colors
                ${
                  active
                    ? "bg-zinc-800 text-indigo-400"
                    : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300"
                }`}
            >
              <Icon size={18} strokeWidth={active ? 2.2 : 1.6} />
              <span className="truncate">{s.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
