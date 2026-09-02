/* ──────────────────────────────────────────────────────────────────────────
   Inspector -- right-side detail panel.
   Shows contextual information depending on what is currently selected:
   a Shot, a Scene, or a Take.

   Two shapes, chosen by AppLayout:
   * "docked"  the resident right panel. Its empty state is deliberately
     narrow so an unused inspector does not hold a fifth of the screen.
   * "drawer"  an overlay sheet for viewports under 1024px, closed by Escape
     or by the scrim. Focus moves into the panel on open and returns to the
     button that opened it; the drawer does not trap focus, so Tab can still
     leave it rather than stranding a keyboard user.
   ────────────────────────────────────────────────────────────────────────── */

import { useEffect, useRef } from "react";
import {
  PanelRightClose,
  PanelRightOpen,
  Camera,
  Layers,
  Clapperboard,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  X,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import StatusBadge from "./StatusBadge";
import TakePreview from "./TakePreview";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import api from "../api/client";
import type { Shot, Scene, Take } from "../types";

// ── Field row helper ─────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      {/* zinc-400 rather than 500/600: on the zinc-950 panel the darker steps
          fall under 4.5:1 in the dark theme. */}
      <dt className="text-[11px] font-medium uppercase tracking-wider text-zinc-400">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-zinc-200 break-words">
        {children || <span className="text-zinc-400 italic">--</span>}
      </dd>
    </div>
  );
}

// ── Sub-panels ───────────────────────────────────────────────────────────

function ShotPanel({ shot }: { shot: Shot }) {
  return (
    <dl className="space-y-1">
      <div className="mb-3 flex items-center gap-2">
        <Camera size={14} className="text-zinc-400" />
        <span className="text-sm font-semibold text-zinc-100">Shot Details</span>
        <StatusBadge status={shot.status} />
      </div>
      <Field label="Shot Type">{shot.shot_type}</Field>
      <Field label="Camera Angle">{shot.camera_angle}</Field>
      <Field label="Camera Movement">{shot.camera_movement}</Field>
      <Field label="Lens / Framing">{shot.lens_framing}</Field>
      <Field label="Subject">{shot.subject}</Field>
      <Field label="Action">{shot.action}</Field>
      <Field label="Environment">{shot.environment}</Field>
      <Field label="Dialogue">{shot.dialogue}</Field>
      <Field label="Duration">{shot.planned_duration_sec}s</Field>
      <Field label="Generation Mode">{shot.generation_mode}</Field>
      <Field label="Seed Policy">{shot.seed_policy}</Field>

      <div className="mt-4 border-t border-zinc-800 pt-3">
        <div className="mb-2 flex items-center gap-2">
          <Layers size={14} className="text-zinc-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Prompt Layers
          </span>
        </div>
        <Field label="Image Prompt">{shot.image_prompt}</Field>
        <Field label="Video Prompt">{shot.video_prompt}</Field>
        <Field label="Negative Prompt">{shot.negative_prompt}</Field>
      </div>
    </dl>
  );
}

function ScenePanel({ scene }: { scene: Scene }) {
  return (
    <dl className="space-y-1">
      <div className="mb-3 flex items-center gap-2">
        <Clapperboard size={14} className="text-zinc-400" />
        <span className="text-sm font-semibold text-zinc-100">Scene Details</span>
        <StatusBadge status={scene.status} />
      </div>
      <Field label="Title">{scene.title}</Field>
      <Field label="Purpose">{scene.purpose}</Field>
      <Field label="Summary">{scene.summary}</Field>
      <Field label="Emotional Beat">{scene.emotional_beat}</Field>
      <Field label="Time of Day">{scene.time_of_day}</Field>
      <Field label="Duration">{scene.planned_duration_sec}s</Field>
      <Field label="Characters">{(scene.character_ids || []).length} assigned</Field>
    </dl>
  );
}

function TakePanel({ take }: { take: Take }) {
  const qc = useQueryClient();

  const approveMut = useMutation({
    mutationFn: () => api.review.approve(take.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["takes"] });
    },
  });

  const rejectMut = useMutation({
    mutationFn: () => api.review.reject(take.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["takes"] });
    },
  });

  const regenMut = useMutation({
    mutationFn: () => api.review.regenerate(take.shot_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["takes"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  return (
    <dl className="space-y-1">
      <div className="mb-3 flex items-center gap-2">
        <Clapperboard size={14} className="text-zinc-400" />
        <span className="text-sm font-semibold text-zinc-100">Take Details</span>
        <StatusBadge status={take.review_status} />
      </div>

      <TakePreview take={take} className="mb-3" />

      <Field label="File">{take.file_path || "N/A"}</Field>
      <Field label="Resolution">
        {take.width && take.height ? `${take.width}x${take.height}` : "--"}
      </Field>
      <Field label="Duration">{take.duration_sec}s</Field>
      <Field label="Codec">{take.codec}</Field>
      <Field label="Rating">{take.rating ?? "--"}</Field>
      <Field label="Notes">{take.notes}</Field>

      {take.review_status === "Pending" && (
        <div className="mt-4 flex gap-2 border-t border-zinc-800 pt-3">
          <button
            onClick={() => approveMut.mutate()}
            disabled={approveMut.isPending}
            className="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md bg-green-700 px-3 text-xs font-medium text-green-50 hover:bg-green-600 disabled:opacity-50"
          >
            <ThumbsUp size={14} /> Approve
          </button>
          <button
            onClick={() => rejectMut.mutate()}
            disabled={rejectMut.isPending}
            className="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md bg-red-800 px-3 text-xs font-medium text-red-50 hover:bg-red-700 disabled:opacity-50"
          >
            <ThumbsDown size={14} /> Reject
          </button>
        </div>
      )}

      <button
        onClick={() => regenMut.mutate()}
        disabled={regenMut.isPending}
        className="mt-2 flex h-9 w-full items-center justify-center gap-1.5 rounded-md border border-zinc-700 px-3 text-xs font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
      >
        <RefreshCw size={14} /> Regenerate
      </button>
    </dl>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────

function EmptyInspector() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-3 text-center">
      <div className="mb-2 rounded-lg bg-zinc-800 p-3">
        <Layers size={20} className="text-zinc-400" />
      </div>
      <p className="text-xs text-zinc-400">
        Select a scene, shot, or take to inspect it.
      </p>
    </div>
  );
}

// ── Main Inspector component ─────────────────────────────────────────────

export default function Inspector({
  variant = "docked",
}: {
  variant?: "docked" | "drawer";
}) {
  const { inspectorOpen, currentProjectId, selectedShotId, selectedSceneId, selectedTakeId } =
    useAppState();
  const dispatch = useAppDispatch();
  const panelRef = useRef<HTMLElement>(null);

  // Fetch selected entities when IDs are present.
  // We call the shots endpoint with scene context. Because we may not always know
  // the sceneId for a shot, we use a simplified approach: fetch all scenes and
  // find the shot within them if needed.

  const { data: selectedScene } = useQuery({
    queryKey: ["scene", currentProjectId, selectedSceneId],
    queryFn: () => api.scenes.get(currentProjectId!, selectedSceneId!),
    enabled: !!currentProjectId && !!selectedSceneId,
  });

  const { data: selectedTake } = useQuery({
    queryKey: ["take", currentProjectId, selectedTakeId],
    queryFn: () => api.review.getTake(selectedTakeId!),
    enabled: !!selectedTakeId,
  });

  // For shots, we need the sceneId. We rely on selectedSceneId being set alongside selectedShotId.
  const { data: selectedShot } = useQuery({
    queryKey: ["shot", currentProjectId, selectedSceneId, selectedShotId],
    queryFn: () =>
      api.shots.get(currentProjectId!, selectedSceneId!, selectedShotId!),
    enabled: !!currentProjectId && !!selectedSceneId && !!selectedShotId,
  });

  const isDrawer = variant === "drawer";
  const close = () => dispatch({ type: "SET_INSPECTOR", open: false });

  // Escape closes the drawer. Only bound while it is open, so the key stays
  // free for the pages underneath the rest of the time.
  useEffect(() => {
    if (!isDrawer || !inspectorOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dispatch({ type: "SET_INSPECTOR", open: false });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isDrawer, inspectorOpen, dispatch]);

  // Move focus into the sheet on open, and hand it back to the toggle on
  // close -- but only if focus is still inside the sheet, so a resize that
  // swaps the variant does not yank focus away from wherever the user is.
  useEffect(() => {
    if (!isDrawer || !inspectorOpen) return;
    const panel = panelRef.current;
    panel?.focus();
    return () => {
      if (!panel?.contains(document.activeElement)) return;
      document.querySelector<HTMLElement>("[data-inspector-toggle]")?.focus();
    };
  }, [isDrawer, inspectorOpen]);

  // Determine what to show -- priority: take > shot > scene > empty
  let content: React.ReactNode = <EmptyInspector />;
  let hasSelection = false;

  if (selectedTakeId && selectedTake) {
    content = <TakePanel take={selectedTake} />;
    hasSelection = true;
  } else if (selectedShotId && selectedShot) {
    content = <ShotPanel shot={selectedShot} />;
    hasSelection = true;
  } else if (selectedSceneId && selectedScene) {
    content = <ScenePanel scene={selectedScene} />;
    hasSelection = true;
  }

  const header = (
    <div className="flex h-11 shrink-0 items-center border-b border-zinc-800 px-3">
      <h2 className="flex-1 text-xs font-semibold uppercase tracking-wider text-zinc-300">
        Inspector
      </h2>
      <button
        type="button"
        onClick={close}
        title="Close inspector"
        className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
      >
        {isDrawer ? <X size={16} /> : <PanelRightClose size={16} />}
        <span className="sr-only">Close inspector</span>
      </button>
    </div>
  );

  if (isDrawer) {
    if (!inspectorOpen) return null;

    return (
      <div className="fixed inset-0 z-40 flex">
        {/* A literal black scrim: the light theme mirrors the zinc ramp, so a
            zinc-950 overlay would be white there and read as a flash. */}
        <div
          role="presentation"
          onClick={close}
          className="flex-1 bg-black/50 backdrop-blur-[1px]"
        />
        <aside
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label="Inspector"
          className="flex h-full w-[min(360px,88vw)] flex-col bg-zinc-950 shadow-2xl outline-none panel-border-l"
        >
          {header}
          <div className="flex-1 overflow-y-auto px-3 py-3">{content}</div>
        </aside>
      </div>
    );
  }

  if (!inspectorOpen) {
    return (
      <aside className="flex w-11 shrink-0 flex-col items-center bg-zinc-950 pt-3 panel-border-l transition-panel">
        <button
          type="button"
          data-inspector-toggle
          onClick={() => dispatch({ type: "TOGGLE_INSPECTOR" })}
          aria-expanded={false}
          title="Expand inspector"
          className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        >
          <PanelRightOpen size={16} />
          <span className="sr-only">Expand inspector</span>
        </button>
      </aside>
    );
  }

  return (
    // The empty inspector shrinks to 208px: wide enough to explain itself,
    // narrow enough that an unused panel is not holding a fifth of a 1440px
    // screen (UI audit P1 #5).
    <aside
      aria-label="Inspector"
      className={`flex shrink-0 flex-col overflow-hidden bg-zinc-950 panel-border-l transition-panel ${
        hasSelection ? "w-[350px]" : "w-[208px]"
      }`}
    >
      {header}
      <div className="flex-1 overflow-y-auto px-4 py-3">{content}</div>
    </aside>
  );
}
