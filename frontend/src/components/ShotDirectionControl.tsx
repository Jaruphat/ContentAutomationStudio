import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { toAIError } from "../api/client";
import type { Shot } from "../types";

/**
 * What a clip does, how the camera behaves, and what it sounds like.
 *
 * Three boxes rather than one, because the video model does not weigh them
 * evenly: given a sentence about the camera it takes that as the whole brief
 * and animates nothing, and given the sound first it describes the scene from
 * the ear. Kept in this order on screen because that is the order they are
 * sent in.
 *
 * Unlike the clip audio control beside it, saving here changes what would be
 * generated - an approved take of this shot becomes a take of a shot that no
 * longer exists. The button says so before it is pressed.
 */
export default function ShotDirectionControl({
  shot,
  projectId,
}: {
  shot: Shot;
  projectId: string;
}) {
  const [subject, setSubject] = useState(shot.subject_motion ?? "");
  const [camera, setCamera] = useState(shot.camera_motion ?? "");
  const [audio, setAudio] = useState(shot.audio_direction ?? "");
  const qc = useQueryClient();

  const save = useMutation({
    mutationFn: () =>
      api.shots.update(projectId, shot.scene_id, shot.id, {
        subject_motion: subject,
        camera_motion: camera,
        audio_direction: audio,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shot", projectId] });
      qc.invalidateQueries({ queryKey: ["shots", projectId] });
      qc.invalidateQueries({ queryKey: ["preflight", projectId] });
    },
  });

  const changed =
    subject !== (shot.subject_motion ?? "") ||
    camera !== (shot.camera_motion ?? "") ||
    audio !== (shot.audio_direction ?? "");
  const cameraOnly = !subject.trim() && camera.trim().length > 0;
  const box =
    "mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100";

  return (
    <div className="my-4 space-y-2 rounded border border-zinc-700 p-3">
      <p className="text-xs font-medium text-zinc-300">Clip direction</p>
      <label className="block text-xs text-zinc-400">
        What happens in the frame
        <textarea
          aria-label="What happens in the frame"
          rows={3}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          className={box}
        />
      </label>
      <label className="block text-xs text-zinc-400">
        How the camera behaves
        <textarea
          aria-label="How the camera behaves"
          rows={2}
          value={camera}
          onChange={(e) => setCamera(e.target.value)}
          className={box}
        />
      </label>
      <label className="block text-xs text-zinc-400">
        What it sounds like
        <textarea
          aria-label="What it sounds like"
          rows={2}
          value={audio}
          onChange={(e) => setAudio(e.target.value)}
          className={box}
        />
      </label>
      {cameraOnly && (
        <p className="rounded border border-amber-900/60 bg-amber-950/30 p-1.5 text-[11px] leading-snug text-amber-200">
          This describes only how the camera behaves. A video model reads that
          as the whole brief and usually animates nothing - name what moves,
          what changes, what a viewer would see occur.
        </p>
      )}
      <p className="text-[11px] text-zinc-400">
        This is sent to the model, so saving it marks any clip already
        generated for this shot as out of date.
      </p>
      <button
        type="button"
        disabled={!changed || save.isPending}
        onClick={() => save.mutate()}
        className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50"
      >
        {save.isPending ? "Saving…" : "Save direction"}
      </button>
      {save.isSuccess && (
        <p role="status" className="text-xs text-emerald-400">
          Saved. Generate this shot again to see the change.
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-xs text-red-300">
          {toAIError(save.error).detail}
        </p>
      )}
    </div>
  );
}
