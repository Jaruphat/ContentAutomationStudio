/* ──────────────────────────────────────────────────────────────────────────
   StoryboardPage -- Scene + Shot grid / table view.
   Expandable scene cards that reveal shots underneath.
   Inline editing, add / delete, and status indicators.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LayoutGrid,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  Loader2,
  GripVertical,
  Camera,
  Save,
  AlertCircle,
} from "lucide-react";
import api from "../api/client";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import StatusBadge from "../components/StatusBadge";
import AIGenerationPanel from "../components/AIGenerationPanel";
import MediaProviderFields from "../components/MediaProviderFields";
import type { MediaProviderId, Scene, Shot, ShotCreate } from "../types";

// ── Shot row ─────────────────────────────────────────────────────────────

function ShotRow({
  shot,
  projectId,
  sceneId,
  isSelected,
  onSelect,
}: {
  shot: Shot;
  projectId: string;
  sceneId: string;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [shotType, setShotType] = useState(shot.shot_type);
  const [cameraAngle, setCameraAngle] = useState(shot.camera_angle);
  const [cameraMovement, setCameraMovement] = useState(shot.camera_movement);
  const [subject, setSubject] = useState(shot.subject);
  const [action, setAction] = useState(shot.action);
  const [imagePrompt, setImagePrompt] = useState(shot.image_prompt);
  const [duration, setDuration] = useState(String(shot.planned_duration_sec));
  const [genMode, setGenMode] = useState(shot.generation_mode);
  const [imageProviderId, setImageProviderId] = useState<MediaProviderId>(
    shot.image_provider_id ?? "comfyui",
  );
  const [imageModel, setImageModel] = useState(shot.image_model || "workflow");

  const mediaProvidersQ = useQuery({
    queryKey: ["media-providers"],
    queryFn: api.media.providers,
  });

  const updateMut = useMutation({
    mutationFn: (data: Partial<ShotCreate>) =>
      api.shots.update(projectId, sceneId, shot.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shots", projectId, sceneId] });
      setEditing(false);
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => api.shots.delete(projectId, sceneId, shot.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["shots", projectId, sceneId] }),
  });

  if (editing) {
    return (
      <tr className="border-t border-zinc-800 bg-zinc-800/40">
        <td colSpan={7} className="px-3 py-3">
          <div className="space-y-2">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Type</label>
                <input value={shotType} onChange={(e) => setShotType(e.target.value)} className="w-full rounded px-2 py-1 text-xs" placeholder="wide, close-up..." />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Camera Angle</label>
                <input value={cameraAngle} onChange={(e) => setCameraAngle(e.target.value)} className="w-full rounded px-2 py-1 text-xs" placeholder="eye level..." />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Camera Movement</label>
                <input value={cameraMovement} onChange={(e) => setCameraMovement(e.target.value)} className="w-full rounded px-2 py-1 text-xs" placeholder="pan, dolly..." />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Subject</label>
                <input value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full rounded px-2 py-1 text-xs" />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Action</label>
                <input value={action} onChange={(e) => setAction(e.target.value)} className="w-full rounded px-2 py-1 text-xs" placeholder="character walks..." />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Duration (sec)</label>
                <input value={duration} onChange={(e) => setDuration(e.target.value)} className="w-full rounded px-2 py-1 text-xs" placeholder="5.0" />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">Gen Mode</label>
                <select value={genMode} onChange={(e) => setGenMode(e.target.value as typeof genMode)} className="w-full rounded px-2 py-1 text-xs">
                  <option value="image">Image</option>
                  <option value="video">Video</option>
                  <option value="image-to-video">Image to Video</option>
                </select>
              </div>
            </div>
            <MediaProviderFields
              catalogue={mediaProvidersQ.data}
              generationMode={genMode}
              providerId={imageProviderId}
              model={imageModel}
              onProviderChange={(providerId, defaultModel) => {
                setImageProviderId(providerId);
                setImageModel(defaultModel);
              }}
              onModelChange={setImageModel}
            />
            <div>
              <label className="text-[10px] text-zinc-500 uppercase">Image Prompt</label>
              <textarea value={imagePrompt} onChange={(e) => setImagePrompt(e.target.value)} className="w-full rounded px-2 py-1 text-xs" rows={2} />
            </div>
            <div className="flex justify-end gap-1">
              <button
                onClick={() => setEditing(false)}
                className="rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  updateMut.mutate({
                    shot_type: shotType,
                    camera_angle: cameraAngle,
                    camera_movement: cameraMovement,
                    subject,
                    action,
                    image_prompt: imagePrompt,
                    planned_duration_sec: parseFloat(duration) || 0,
                    generation_mode: genMode,
                    image_provider_id: imageProviderId,
                    image_model: imageModel,
                  })
                }
                disabled={updateMut.isPending}
                className="flex items-center gap-1 rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {updateMut.isPending ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                Save
              </button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      onClick={onSelect}
      className={`cursor-pointer border-t border-zinc-800 transition-colors ${
        isSelected ? "bg-indigo-950/30" : "hover:bg-zinc-800/40"
      }`}
    >
      <td className="px-2 py-2 text-center">
        <div className="flex items-center justify-center gap-1">
          <GripVertical size={12} className="text-zinc-600" />
          <span className="text-xs text-zinc-500">{shot.order + 1}</span>
        </div>
      </td>
      <td className="px-2 py-2 text-xs text-zinc-300">{shot.shot_type || "--"}</td>
      <td className="px-2 py-2 text-xs text-zinc-300">
        {shot.camera_angle || "--"}
        {shot.camera_movement && (
          <span className="ml-1 text-zinc-500">({shot.camera_movement})</span>
        )}
      </td>
      <td className="px-2 py-2 text-xs text-zinc-300">{shot.subject || "--"}</td>
      <td className="max-w-[200px] px-2 py-2 text-xs text-zinc-400 truncate">
        {shot.image_prompt || shot.video_prompt || "--"}
      </td>
      <td className="px-2 py-2">
        <StatusBadge status={shot.status} />
      </td>
      <td className="px-2 py-2">
        <div className="flex gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setEditing(true);
            }}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300"
          >
            <Camera size={13} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              deleteMut.mutate();
            }}
            className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Scene card ───────────────────────────────────────────────────────────

function SceneCard({
  scene,
  projectId,
}: {
  scene: Scene;
  projectId: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const { selectedShotId } = useAppState();
  const dispatch = useAppDispatch();
  const qc = useQueryClient();

  const shotsQ = useQuery({
    queryKey: ["shots", projectId, scene.id],
    queryFn: () => api.shots.list(projectId, scene.id),
    enabled: expanded,
  });

  const deleteSceneMut = useMutation({
    mutationFn: () => api.scenes.delete(projectId, scene.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["scenes", projectId] }),
  });

  const addShotMut = useMutation({
    mutationFn: () =>
      api.shots.create(projectId, scene.id, {
        order: (shotsQ.data?.length ?? 0),
        shot_type: "wide",
        generation_mode: "image",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["shots", projectId, scene.id] }),
  });

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 overflow-hidden">
      {/* Scene header */}
      <div className="flex items-center gap-2 bg-zinc-800/40 px-4 py-2.5">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-zinc-500 hover:text-zinc-300"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button
          onClick={() => {
            dispatch({ type: "SELECT_SCENE", id: scene.id });
          }}
          className="flex-1 text-left"
        >
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
            Scene {scene.order + 1}
          </span>
          <span className="ml-2 text-sm text-zinc-200">
            {scene.title || "Untitled"}
          </span>
          {scene.summary && (
            <span className="ml-2 text-xs text-zinc-500 truncate">
              -- {scene.summary}
            </span>
          )}
        </button>
        <StatusBadge status={scene.status} />
        <span className="text-[10px] text-zinc-500">
          {scene.planned_duration_sec}s
        </span>
        <button
          onClick={() => deleteSceneMut.mutate()}
          className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
          title="Delete scene"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {/* Shots table */}
      {expanded && (
        <div className="px-2 pb-2">
          {shotsQ.isLoading && (
            <div className="flex items-center gap-2 px-4 py-4 text-sm text-zinc-500">
              <Loader2 size={14} className="animate-spin" /> Loading shots...
            </div>
          )}

          {shotsQ.data && shotsQ.data.length === 0 && (
            <p className="px-4 py-4 text-sm text-zinc-500 italic">
              No shots in this scene yet.
            </p>
          )}

          {shotsQ.data && shotsQ.data.length > 0 && (
            <table className="w-full text-left">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-zinc-500">
                  <th className="w-10 px-2 py-1.5">#</th>
                  <th className="px-2 py-1.5">Type</th>
                  <th className="px-2 py-1.5">Camera</th>
                  <th className="px-2 py-1.5">Subject</th>
                  <th className="px-2 py-1.5">Prompt</th>
                  <th className="px-2 py-1.5">Status</th>
                  <th className="w-16 px-2 py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {shotsQ.data.map((shot) => (
                  <ShotRow
                    key={shot.id}
                    shot={shot}
                    projectId={projectId}
                    sceneId={scene.id}
                    isSelected={selectedShotId === shot.id}
                    onSelect={() => {
                      dispatch({ type: "SELECT_SCENE", id: scene.id });
                      dispatch({ type: "SELECT_SHOT", id: shot.id });
                    }}
                  />
                ))}
              </tbody>
            </table>
          )}

          <button
            onClick={() => addShotMut.mutate()}
            disabled={addShotMut.isPending}
            className="mt-2 ml-2 flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50"
          >
            {addShotMut.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Plus size={12} />
            )}
            Add Shot
          </button>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// StoryboardPage
// ══════════════════════════════════════════════════════════════════════════

export default function StoryboardPage() {
  const { currentProjectId } = useAppState();
  const qc = useQueryClient();

  const scenesQ = useQuery({
    queryKey: ["scenes", currentProjectId],
    queryFn: () => api.scenes.list(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const addSceneMut = useMutation({
    mutationFn: () =>
      api.scenes.create(currentProjectId!, {
        order: scenesQ.data?.length ?? 0,
        title: `Scene ${(scenesQ.data?.length ?? 0) + 1}`,
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["scenes", currentProjectId] }),
  });

  // ── No project selected ──────────────────────────────────────────────
  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <LayoutGrid size={32} className="mb-3 text-zinc-600" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LayoutGrid size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Storyboard</h1>
          {scenesQ.data && (
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
              {scenesQ.data.length} scene{scenesQ.data.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <button
          onClick={() => addSceneMut.mutate()}
          disabled={addSceneMut.isPending}
          className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {addSceneMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Plus size={14} />
          )}
          Add Scene
        </button>
      </div>

      {/* Loading */}
      <AIGenerationPanel
        title="Generate Storyboard with AI"
        description="Creates a 3-scene, 9–15 shot draft from the saved plot. Existing scenes are never replaced silently."
        buildRequest={(base) => ({ ...base, scene_count: 3, min_shots: 9, max_shots: 15, replace_existing: (scenesQ.data?.length ?? 0) > 0 })}
        run={(request) => api.ai.storyboard(currentProjectId, request)}
        onApplied={() => qc.invalidateQueries({ queryKey: ["scenes", currentProjectId] })}
      />

      {(scenesQ.data?.length ?? 0) > 0 && (
        <AIGenerationPanel
          title="Compile Shot Prompts with AI"
          description="Preview then apply image and video prompts for every existing shot."
          buildRequest={(base) => base}
          run={(request) => api.ai.prompts(currentProjectId, request)}
          onApplied={() => qc.invalidateQueries({ queryKey: ["shots"] })}
        />
      )}

      {scenesQ.isLoading && (
        <div className="flex items-center gap-2 text-zinc-500 py-12 justify-center">
          <Loader2 size={16} className="animate-spin" /> Loading storyboard...
        </div>
      )}

      {/* Error */}
      {scenesQ.isError && (
        <div className="flex items-center gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} /> Failed to load scenes.
        </div>
      )}

      {/* Empty */}
      {scenesQ.data && scenesQ.data.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <LayoutGrid size={28} className="mb-2 text-zinc-600" />
          <p className="text-sm text-zinc-500">
            No scenes yet. Click "Add Scene" to start building your storyboard.
          </p>
        </div>
      )}

      {/* Scene list */}
      <div className="space-y-3">
        {scenesQ.data
          ?.sort((a, b) => a.order - b.order)
          .map((scene) => (
            <SceneCard
              key={scene.id}
              scene={scene}
              projectId={currentProjectId}
            />
          ))}
      </div>
    </div>
  );
}
