import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { toAIError } from "../api/client";
import type { Shot } from "../types";

export default function ShotAudioControl({ shot, projectId }: { shot: Shot; projectId: string }) {
  const [muted, setMuted] = useState(shot.audio_mode === "mute");
  const [gain, setGain] = useState(String(shot.audio_gain_db ?? 0));
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.shots.update(projectId, shot.scene_id, shot.id, {audio_mode: muted ? "mute" : "native", audio_gain_db: Number(gain)}),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:["shot", projectId]});
      qc.invalidateQueries({queryKey:["shots", projectId]});
      qc.invalidateQueries({queryKey:["rendered-film", projectId]});
      qc.invalidateQueries({queryKey:["publish-package", projectId]});
    },
  });
  const valid = gain.trim() !== "" && Number.isFinite(Number(gain)) && Number(gain) >= -60 && Number(gain) <= 12;
  return <div className="my-4 space-y-2 rounded border border-zinc-700 p-3">
    <p className="text-xs font-medium text-zinc-300">Clip audio</p>
    <label className="flex items-center gap-2 text-xs text-zinc-300"><input type="checkbox" checked={muted} onChange={e=>setMuted(e.target.checked)} />Mute this clip's original sound</label>
    <label className="block text-xs text-zinc-400">Level adjustment (dB)
      <input aria-label="Clip audio level in dB" type="number" min="-60" max="12" step="1" value={gain} onChange={e=>setGain(e.target.value)} disabled={muted} className="mt-1 w-full rounded px-2 py-1.5" />
    </label>
    <p className="text-[11px] text-zinc-400">Applies on the next render. Narration stays audible.</p>
    <button type="button" disabled={!valid || save.isPending} onClick={()=>save.mutate()} className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50">{save.isPending ? "Saving…" : "Save clip audio"}</button>
    {save.isSuccess && <p role="status" className="text-xs text-emerald-400">Saved. Render again to hear the change.</p>}
    {save.isError && <p role="alert" className="text-xs text-red-300">{toAIError(save.error).detail}</p>}
  </div>;
}
