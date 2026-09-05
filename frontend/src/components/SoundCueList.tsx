/* ──────────────────────────────────────────────────────────────────────────
   SoundCueList -- a sound, a place in the cut, and a level.

   The place is given relative to a shot, never as an absolute second. A cue
   pinned to a second detaches from the thing it was made for the first time
   somebody trims an earlier shot, and it detaches silently: the film still
   renders, the door still bangs, just not when the door opens.

   The list shows where each cue *currently* lands, resolved against the cut as
   it stands - so re-editing moves the sounds and the list says where they went.
   ────────────────────────────────────────────────────────────────────────── */

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Plus, Trash2, Volume2 } from "lucide-react";
import api from "../api/client";
import ActionError from "./ActionError";

export default function SoundCueList({
  projectId,
  shots,
}: {
  projectId: string;
  /** The shots on the cut, as the timeline knows them. A cue can only be
   *  anchored to a shot that is actually placed - one that is not has no
   *  moment to be placed at. */
  shots: { id: string; label: string }[];
}) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [shotId, setShotId] = useState("");
  const [offset, setOffset] = useState("0");
  const [gain, setGain] = useState("0");
  const [label, setLabel] = useState("");
  const [uploaded, setUploaded] = useState<{ path: string; name: string } | null>(
    null,
  );

  const cuesQ = useQuery({
    queryKey: ["sound-cues", projectId],
    queryFn: () => api.sound.list(projectId),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.sound.upload(projectId, file),
    onSuccess: (result) => {
      setUploaded({ path: result.file_path, name: result.original_filename });
      if (!label) setLabel(result.original_filename.replace(/\.[^.]+$/, ""));
    },
  });

  const create = useMutation({
    mutationFn: () =>
      api.sound.create(projectId, {
        shot_id: shotId,
        file_path: uploaded?.path ?? "",
        offset_sec: Number(offset) || 0,
        gain_db: Number(gain) || 0,
        label,
      }),
    onSuccess: () => {
      setUploaded(null);
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      qc.invalidateQueries({ queryKey: ["sound-cues", projectId] });
    },
  });

  const remove = useMutation({
    mutationFn: (cueId: string) => api.sound.remove(projectId, cueId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["sound-cues", projectId] }),
  });

  return (
    <section className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center gap-2">
        <Volume2 size={14} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-zinc-200">Sound cues</h2>
      </div>
      <p className="text-[11px] leading-snug text-zinc-500">
        A sound placed inside a shot. The offset is measured from where that
        shot starts in the cut, so re-editing the film moves the sound with it
        - a cue pinned to an absolute second detaches the first time an earlier
        shot is trimmed, and it does so silently.
      </p>

      <div className="grid gap-2 sm:grid-cols-5">
        <label className="text-xs text-zinc-400 sm:col-span-2">
          Sound file
          <input
            ref={fileRef}
            type="file"
            accept="audio/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
            className="mt-1 w-full text-xs"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Shot
          <select
            value={shotId}
            onChange={(e) => setShotId(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-xs"
          >
            <option value="">Choose a shot</option>
            {shots.map((shot) => (
              <option key={shot.id} value={shot.id}>
                {shot.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zinc-400">
          Offset (sec)
          <input
            value={offset}
            onChange={(e) => setOffset(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-xs"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Gain (dB)
          <input
            value={gain}
            onChange={(e) => setGain(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-xs"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-zinc-400">
          Label
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="pneumatic door"
            className="mt-1 w-56 rounded px-2 py-1 text-xs"
          />
        </label>
        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={create.isPending || !uploaded || !shotId}
          title={
            !uploaded
              ? "Upload a sound first"
              : !shotId
                ? "Choose the shot this sound belongs to"
                : "Place the cue"
          }
          className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {create.isPending || upload.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Plus size={12} />
          )}
          Place cue
        </button>
        {uploaded && (
          <span className="text-[11px] text-zinc-500">{uploaded.name}</span>
        )}
      </div>
      <ActionError label="Upload sound" error={upload.error} />
      <ActionError label="Place sound cue" error={create.error} />

      <ul className="space-y-1">
        {(cuesQ.data ?? []).map((cue) => (
          <li
            key={cue.cue_id}
            className="flex flex-wrap items-center gap-2 rounded border border-zinc-800 px-2 py-1.5 text-xs"
          >
            <span className="font-medium text-zinc-200">
              {cue.label || "sound"}
            </span>
            <span className="text-zinc-500">
              {cue.start_sec === null
                ? "not placed"
                : `at ${cue.start_sec.toFixed(2)}s`}
              {cue.gain_db ? ` · ${cue.gain_db > 0 ? "+" : ""}${cue.gain_db} dB` : ""}
            </span>
            {cue.runs_past_the_end && (
              <span className="text-[10px] text-zinc-500">
                runs past the end
              </span>
            )}
            {cue.problem && (
              <span className="flex items-center gap-1 text-[11px] text-amber-300">
                <AlertTriangle size={11} />
                {cue.problem}
              </span>
            )}
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => remove.mutate(cue.cue_id)}
              className="rounded p-1 text-zinc-500 hover:bg-red-900/40 hover:text-red-300"
              aria-label="Remove cue"
            >
              <Trash2 size={12} />
            </button>
          </li>
        ))}
        {cuesQ.data?.length === 0 && (
          <li className="text-[11px] text-zinc-500">
            No cues. Ambience, a clock tick, a door - the sounds that make a
            generated world sound like a place.
          </li>
        )}
      </ul>
    </section>
  );
}
