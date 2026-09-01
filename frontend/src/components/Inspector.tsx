/* ──────────────────────────────────────────────────────────────────────────
   Inspector -- collapsible right-side detail panel.
   Shows contextual information depending on what is currently selected:
   a Shot, a Scene, or a Take.
   ────────────────────────────────────────────────────────────────────────── */

import {
  PanelRightClose,
  PanelRightOpen,
  Camera,
  Layers,
  Clapperboard,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import StatusBadge from "./StatusBadge";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import api from "../api/client";
import type { Shot, Scene, Take } from "../types";

// ── Field row helper ─────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <dt className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-zinc-200 break-words">{children || <span className="text-zinc-600 italic">--</span>}</dd>
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

      {/* Thumbnail placeholder */}
      <div className="mb-3 flex h-36 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800 text-xs text-zinc-500">
        {take.thumbnail_path ? (
          <span className="truncate px-2">{take.thumbnail_path}</span>
        ) : (
          "No preview available"
        )}
      </div>

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
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-green-700 px-3 py-1.5 text-xs font-medium text-green-100 hover:bg-green-600 disabled:opacity-50"
          >
            <ThumbsUp size={13} /> Approve
          </button>
          <button
            onClick={() => rejectMut.mutate()}
            disabled={rejectMut.isPending}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-red-800 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-700 disabled:opacity-50"
          >
            <ThumbsDown size={13} /> Reject
          </button>
        </div>
      )}

      <button
        onClick={() => regenMut.mutate()}
        disabled={regenMut.isPending}
        className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
      >
        <RefreshCw size={13} /> Regenerate
      </button>
    </dl>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────

function EmptyInspector() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 text-center">
      <div className="mb-2 rounded-lg bg-zinc-800 p-3">
        <Layers size={20} className="text-zinc-500" />
      </div>
      <p className="text-sm text-zinc-500">
        Select a scene, shot, or take to inspect its details here.
      </p>
    </div>
  );
}

// ── Main Inspector component ─────────────────────────────────────────────

export default function Inspector() {
  const { inspectorOpen, currentProjectId, selectedShotId, selectedSceneId, selectedTakeId } =
    useAppState();
  const dispatch = useAppDispatch();

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

  const toggleBtn = (
    <button
      onClick={() => dispatch({ type: "TOGGLE_INSPECTOR" })}
      className="absolute top-3 right-3 z-10 rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
      title={inspectorOpen ? "Collapse inspector" : "Expand inspector"}
    >
      {inspectorOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
    </button>
  );

  if (!inspectorOpen) {
    return (
      <aside className="relative flex w-10 flex-col items-center bg-zinc-950 pt-12 panel-border-l transition-panel">
        {toggleBtn}
      </aside>
    );
  }

  // Determine what to show -- priority: take > shot > scene > empty
  let content: React.ReactNode = <EmptyInspector />;

  if (selectedTakeId && selectedTake) {
    content = (
      <TakePanel take={selectedTake} />
    );
  } else if (selectedShotId && selectedShot) {
    content = <ShotPanel shot={selectedShot} />;
  } else if (selectedSceneId && selectedScene) {
    content = <ScenePanel scene={selectedScene} />;
  }

  return (
    <aside className="relative flex w-[350px] shrink-0 flex-col overflow-hidden bg-zinc-950 panel-border-l transition-panel">
      {toggleBtn}
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Inspector
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">{content}</div>
    </aside>
  );
}
