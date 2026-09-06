/* ──────────────────────────────────────────────────────────────────────────
   StageRail -- production stage navigation.
   Each stage maps to a route; the active stage is highlighted.

   Two shapes, chosen by AppLayout from the viewport width:
   * "rail" -- the vertical left rail used from 768px up.
   * "bar"  -- a bottom tab bar for phone widths, where an 88px rail would eat
     a quarter of the screen. Same stages, same order, so nothing is ever out
     of reach.
   ────────────────────────────────────────────────────────────────────────── */

import { useLocation, useNavigate } from "react-router-dom";
import {
  BookOpen,
  LayoutGrid,
  Zap,
  CheckCircle,
  Film,
  Download,
  Settings2,
  Monitor,
  Sun,
  Moon,
  PanelRight,
  Radio,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTheme, type ThemePreference } from "../theme";
import { useAppState, useAppDispatch } from "../store/useProjectStore";

interface Stage {
  label: string;
  path: string;
  icon: LucideIcon;
}

const stages: Stage[] = [
  { label: "Channel", path: "/channel", icon: Radio },
  { label: "Story", path: "/story", icon: BookOpen },
  { label: "Storyboard", path: "/storyboard", icon: LayoutGrid },
  { label: "Generate", path: "/generate", icon: Zap },
  { label: "Review", path: "/review", icon: CheckCircle },
  { label: "Timeline", path: "/timeline", icon: Film },
  { label: "Export", path: "/export", icon: Download },
  { label: "Workflows", path: "/workflows", icon: Settings2 },
];

const themeOptions: { value: ThemePreference; label: string; icon: LucideIcon }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

/**
 * System / Light / Dark as three labelled buttons rather than a <select>.
 * A select in a narrow rail collapses to an unreadable stub and hides the
 * current choice behind a popup; three toggle buttons keep the state visible,
 * reachable by Tab, and comfortably above the 32px minimum hit size.
 *
 * "compact" drops the text labels for the phone top bar, where the accessible
 * name comes from the sr-only span and the tooltip.
 */
export function ThemeControl({ compact = false }: { compact?: boolean }) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      role="group"
      aria-label="Color theme"
      className={compact ? "flex items-center gap-0.5" : "flex flex-col items-stretch gap-0.5"}
    >
      {themeOptions.map((option) => {
        const Icon = option.icon;
        const selected = preference === option.value;

        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setPreference(option.value)}
            aria-pressed={selected}
            title={`${option.label} theme`}
            className={`flex items-center justify-center gap-1.5 rounded-md transition-colors ${
              compact ? "h-9 w-9" : "h-9 w-full px-2"
            } ${
              selected
                ? "bg-zinc-800 text-indigo-400"
                : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
            }`}
          >
            <Icon size={15} strokeWidth={selected ? 2.2 : 1.7} />
            {compact ? (
              <span className="sr-only">{option.label} theme</span>
            ) : (
              <span className="text-[12px] leading-none">{option.label}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Opens the inspector drawer from the rail on tablet widths. */
function InspectorToggle() {
  const { inspectorOpen } = useAppState();
  const dispatch = useAppDispatch();

  return (
    <button
      type="button"
      data-inspector-toggle
      onClick={() => dispatch({ type: "TOGGLE_INSPECTOR" })}
      aria-expanded={inspectorOpen}
      title="Inspector"
      className="mb-3 flex h-11 w-full flex-col items-center justify-center gap-1 rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
    >
      <PanelRight size={18} strokeWidth={1.7} />
      <span className="text-[12px] leading-none">Inspect</span>
    </button>
  );
}

export default function StageRail({
  variant = "rail",
  showInspectorToggle = false,
}: {
  variant?: "rail" | "bar";
  showInspectorToggle?: boolean;
}) {
  const location = useLocation();
  const navigate = useNavigate();

  if (variant === "bar") {
    return (
      <nav
        aria-label="Production stages"
        className="flex shrink-0 items-stretch border-t border-zinc-800 bg-zinc-950 select-none"
      >
        {stages.map((s) => {
          const active = location.pathname.startsWith(s.path);
          const Icon = s.icon;

          return (
            <button
              key={s.path}
              onClick={() => navigate(s.path)}
              aria-current={active ? "page" : undefined}
              title={s.label}
              className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-1 px-0.5 py-2 transition-colors ${
                active ? "text-indigo-400" : "text-zinc-400 active:bg-zinc-800/60"
              }`}
              /* 52px keeps the tap target above the 44px minimum on a 390px
                 phone, where six tabs already share the full width. */
              style={{ minHeight: 52 }}
            >
              <Icon size={19} strokeWidth={active ? 2.2 : 1.7} />
              <span className="w-full truncate text-center text-[12px] leading-none tracking-tight">
                {s.label}
              </span>
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <nav
      aria-label="Production stages"
      className="flex h-full w-[88px] shrink-0 flex-col items-center bg-zinc-950 px-1 py-3 panel-border-r select-none"
    >
      <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">
        CA
      </div>

      <div className="flex flex-1 flex-col gap-1 self-stretch">
        {stages.map((s) => {
          const active = location.pathname.startsWith(s.path);
          const Icon = s.icon;

          return (
            <button
              key={s.path}
              onClick={() => navigate(s.path)}
              aria-current={active ? "page" : undefined}
              title={s.label}
              /* min-h keeps every stage at the 44px minimum hit area even
                 though the icon and label together measure less. */
              className={`flex min-h-[48px] w-full flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-xs leading-tight transition-colors
                ${
                  active
                    ? "bg-zinc-800 text-indigo-400"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                }`}
            >
              <Icon size={19} strokeWidth={active ? 2.2 : 1.6} />
              <span className="w-full truncate text-center tracking-tight">{s.label}</span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 w-full border-t border-zinc-800 pt-3">
        {showInspectorToggle && <InspectorToggle />}
        <p className="mb-1 text-center text-[12px] font-medium uppercase tracking-wider text-zinc-400">
          Theme
        </p>
        <ThemeControl />
      </div>
    </nav>
  );
}
