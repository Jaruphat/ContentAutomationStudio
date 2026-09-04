import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Loader2, RefreshCw, Unlink } from "lucide-react";
import api from "../api/client";
import type { CharacterSet, ContinuityCandidate } from "../types";
import ActionError from "./ActionError";
import ImagePreview from "./ImagePreview";

export function ShotCharacterBinding({ sets, assignedIds, onChange }: {
  sets: CharacterSet[];
  assignedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const eligible = sets.filter((set) => set.approved_version_id && set.approved_version_is_current);
  const assigned = assignedIds
    .map((id) => sets.find((set) => set.id === id))
    .filter(Boolean) as CharacterSet[];

  return (
    <section aria-label="Shot character sets" className="space-y-2 rounded border border-zinc-700 p-3">
      <div className="flex items-center gap-2">
        <Link2 size={13} />
        <h3 className="text-xs font-semibold uppercase">Character sets</h3>
      </div>
      <p className="text-xs text-zinc-500">
        Only approved, current character sets can be added. Multiple characters are preserved in the selected order.
      </p>
      {assigned.map((set) => (
        <div key={set.id} className={`flex items-center gap-2 rounded p-2 text-xs ${set.approved_version_is_current ? "bg-zinc-800" : "border border-amber-800 bg-amber-950/30 text-amber-300"}`}>
          <span className="flex-1">{set.name}{!set.approved_version_is_current ? " · stale approved version" : " · approved current"}</span>
          <button type="button" aria-label={`Remove ${set.name}`} onClick={() => onChange(assignedIds.filter((id) => id !== set.id))}>
            <Unlink size={13} />
          </button>
        </div>
      ))}
      <label className="block text-xs text-zinc-400">
        Add approved character set
        <select value="" onChange={(event) => event.target.value && onChange([...assignedIds, event.target.value])} className="mt-1 w-full rounded px-2 py-1">
          <option value="">Choose a character set…</option>
          {eligible.filter((set) => !assignedIds.includes(set.id)).map((set) => (
            <option key={set.id} value={set.id}>{set.name}</option>
          ))}
        </select>
      </label>
      {assignedIds.some((id) => !sets.some((set) => set.id === id)) && (
        <p role="alert" className="text-xs text-amber-300">
          A previously bound character set is missing. Remove it before generation.
        </p>
      )}
    </section>
  );
}

const IMAGE_SOURCE = "approved_image_take";
const VIDEO_SOURCE = "approved_video_end_frame";

function CandidatePicker({
  candidates,
  value,
  onChange,
  sourceType,
}: {
  candidates: ContinuityCandidate[];
  value: string;
  onChange: (value: string) => void;
  sourceType: typeof IMAGE_SOURCE | typeof VIDEO_SOURCE;
}) {
  const label = sourceType === IMAGE_SOURCE
    ? "Choose an approved scene image take"
    : "Choose a previous approved video take";
  return (
    <label className="block text-xs text-zinc-400">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded px-2 py-1">
        <option value="">Choose a source take…</option>
        {candidates.map((candidate) => (
          <option key={candidate.take_id} value={candidate.take_id}>
            {candidate.source_label} · {candidate.shot_label} · take {candidate.take_id.slice(0, 8)}
            {candidate.frame ? ` · ${candidate.frame.frame_time_sec.toFixed(2)}s` : " · capture required"}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ShotContinuityControls({ projectId, sceneId, shotId }: {
  projectId: string;
  sceneId: string;
  shotId: string;
}) {
  const queryClient = useQueryClient();
  const [selectedImageTakeId, setSelectedImageTakeId] = useState("");
  const [selectedVideoTakeId, setSelectedVideoTakeId] = useState("");
  const [selectedEndTakeId, setSelectedEndTakeId] = useState("");
  const key = ["continuity", projectId, sceneId, shotId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.continuity.get(projectId, sceneId, shotId),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const captureAndBind = useMutation({
    mutationFn: async (takeId: string) => {
      await api.continuity.extract(projectId, takeId);
      return api.continuity.bind(projectId, sceneId, shotId, takeId);
    },
    onSuccess: refresh,
  });
  const extract = useMutation({
    mutationFn: (takeId: string) => api.continuity.extract(projectId, takeId),
    onSuccess: refresh,
  });
  const clear = useMutation({
    mutationFn: () => api.continuity.clear(projectId, sceneId, shotId),
    onSuccess: refresh,
  });
  const captureAndLand = useMutation({
    mutationFn: async (takeId: string) => {
      await api.continuity.extract(projectId, takeId);
      return api.continuity.bindEndFrame(projectId, sceneId, shotId, takeId);
    },
    onSuccess: refresh,
  });
  const clearLanding = useMutation({
    mutationFn: () => api.continuity.clearEndFrame(projectId, sceneId, shotId),
    onSuccess: refresh,
  });

  const status = query.data;
  const usable = status?.candidates.filter((candidate) => candidate.usable) ?? [];
  const images = usable.filter((candidate) => candidate.source_type === IMAGE_SOURCE);
  const videos = usable.filter((candidate) => candidate.source_type === VIDEO_SOURCE);
  const boundImage = status?.source_type === IMAGE_SOURCE;
  const mutationError = captureAndBind.error ?? extract.error ?? clear.error
    ?? captureAndLand.error ?? clearLanding.error;
  // Anything approved can be a landing, including a still from a later shot -
  // which is the usual case: the clip has to arrive where the next shot opens.
  const landings = usable.filter((candidate) => candidate.take_id !== status?.source_take_id);

  return (
    <section aria-label="Shot continuity" className="space-y-3 rounded border border-zinc-700 p-3">
      <h3 className="text-xs font-semibold uppercase">Explicit shot continuity</h3>
      <p className="text-xs text-zinc-500">
        Nothing is chained automatically. Explicitly choose the exact approved scene image or a previous approved video end frame that must start this image-to-video shot.
      </p>
      {query.isLoading && (
        <p className="flex items-center gap-1 text-xs text-zinc-400">
          <Loader2 size={12} className="animate-spin" />Loading continuity candidates…
        </p>
      )}
      {query.isError && <ActionError label="Load continuity" error={query.error} />}
      {status && (
        <>
          <div className="space-y-2 rounded bg-zinc-900/40 p-2">
            <CandidatePicker candidates={images} value={selectedImageTakeId} onChange={setSelectedImageTakeId} sourceType={IMAGE_SOURCE} />
            <button
              type="button"
              disabled={!selectedImageTakeId || captureAndBind.isPending}
              onClick={() => captureAndBind.mutate(selectedImageTakeId)}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              Use approved scene image as start frame
            </button>
            {images.length === 0 && <p className="text-xs text-zinc-500">No eligible approved scene image takes are available.</p>}
          </div>
          <div className="space-y-2 rounded bg-zinc-900/40 p-2">
            <CandidatePicker candidates={videos} value={selectedVideoTakeId} onChange={setSelectedVideoTakeId} sourceType={VIDEO_SOURCE} />
            <button
              type="button"
              disabled={!selectedVideoTakeId || captureAndBind.isPending}
              onClick={() => captureAndBind.mutate(selectedVideoTakeId)}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              Use previous approved video end frame
            </button>
            {videos.length === 0 && <p className="text-xs text-zinc-500">No eligible previous approved video takes are available.</p>}
          </div>
          {status.frame && (
            <div className="grid gap-3 rounded bg-zinc-800 p-3 sm:grid-cols-[8rem_1fr]">
              {status.frame.url ? (
                <ImagePreview src={status.frame.url} alt={`Continuity source from ${status.source_shot_label}`} className="h-20 w-32" />
              ) : (
                <div className="flex h-20 w-32 items-center justify-center rounded bg-zinc-900 text-xs text-zinc-500">Thumbnail unavailable</div>
              )}
              <div className="space-y-1 text-xs">
                <p className="font-medium text-zinc-200">
                  Source: {boundImage ? "Approved scene image" : "Previous approved video end frame"} · {status.source_shot_label} · take {status.source_take_id?.slice(0, 8)}
                </p>
                <p className="text-zinc-400">
                  {boundImage
                    ? "Exact approved scene image · start at 0.00s"
                    : `True video end frame · ${status.frame.frame_time_sec.toFixed(2)}s`}
                  {` · ${status.frame.width}×${status.frame.height}`}
                </p>
                <p className="text-[10px] text-zinc-500">
                  Updated {new Date(status.frame.updated_at).toLocaleString()} · SHA {status.frame.sha256.slice(0, 12)}
                </p>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => status.source_take_id && extract.mutate(status.source_take_id)} className="flex items-center gap-1 rounded bg-zinc-700 px-2 py-1">
                    <RefreshCw size={11} />{boundImage ? "Re-capture approved image" : "Re-extract true end frame"}
                  </button>
                  <button type="button" onClick={() => clear.mutate()} className="flex items-center gap-1 rounded bg-zinc-700 px-2 py-1">
                    <Unlink size={11} />Clear continuity
                  </button>
                </div>
              </div>
            </div>
          )}
          <div className="space-y-2 rounded bg-zinc-900/40 p-2">
            <h4 className="text-[11px] font-semibold uppercase text-zinc-300">End frame</h4>
            <p className="text-[11px] text-zinc-500">
              Optional, and only for workflows that accept one. Given both ends the model interpolates between two approved frames, so the cut lands exactly where the next shot opens instead of drifting.
            </p>
            <label className="block text-xs text-zinc-400">
              Choose the approved take this clip has to finish on
              <select aria-label="End frame source" value={selectedEndTakeId} onChange={(event) => setSelectedEndTakeId(event.target.value)} className="mt-1 w-full rounded px-2 py-1">
                <option value="">Choose a landing take…</option>
                {landings.map((candidate) => (
                  <option key={candidate.take_id} value={candidate.take_id}>
                    {candidate.source_label} · {candidate.shot_label} · take {candidate.take_id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={!selectedEndTakeId || captureAndLand.isPending}
              onClick={() => captureAndLand.mutate(selectedEndTakeId)}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              Use as the frame this clip lands on
            </button>
            {landings.length === 0 && <p className="text-xs text-zinc-500">No other approved take is available to land on.</p>}
            {status.end_frame && (
              <div className="grid gap-3 rounded bg-zinc-800 p-3 sm:grid-cols-[8rem_1fr]">
                {status.end_frame.url ? (
                  <ImagePreview src={status.end_frame.url} alt={`End frame from ${status.end_frame_shot_label}`} className="h-20 w-32" />
                ) : (
                  <div className="flex h-20 w-32 items-center justify-center rounded bg-zinc-900 text-xs text-zinc-500">Thumbnail unavailable</div>
                )}
                <div className="space-y-1 text-xs">
                  <p className="font-medium text-zinc-200">
                    Lands on: {status.end_frame_shot_label} · take {status.end_frame_take_id?.slice(0, 8)}
                  </p>
                  <p className="text-[10px] text-zinc-500">
                    {status.end_frame.width}×{status.end_frame.height} · SHA {status.end_frame.sha256.slice(0, 12)}
                  </p>
                  <button type="button" onClick={() => clearLanding.mutate()} className="flex items-center gap-1 rounded bg-zinc-700 px-2 py-1">
                    <Unlink size={11} />Clear end frame
                  </button>
                </div>
              </div>
            )}
          </div>
          {status.problems.length > 0 && (
            <div role="alert" className="rounded border border-red-800 bg-red-950/30 p-2 text-xs text-red-300">
              <strong>Preflight blocker</strong>
              <ul className="mt-1 list-disc pl-4">{status.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>
            </div>
          )}
        </>
      )}
      {mutationError && <ActionError label="Update continuity" error={mutationError} />}
    </section>
  );
}
