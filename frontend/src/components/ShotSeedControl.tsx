import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { toAIError } from "../api/client";
import type { Shot } from "../types";

export default function ShotSeedControl({ shot, projectId }: { shot: Shot; projectId: string }) {
  const [policy, setPolicy] = useState(shot.seed_policy);
  const [seed, setSeed] = useState(String(shot.seed ?? 42));
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.shots.update(projectId, shot.scene_id, shot.id, {
      seed_policy: policy, seed: policy === "fixed" ? Number(seed) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shots", projectId] });
      qc.invalidateQueries({ queryKey: ["shot", projectId] });
    },
  });
  const valid = policy !== "fixed" || (seed.trim() !== "" && Number.isInteger(Number(seed)) && Number(seed) >= 0 && Number(seed) <= 2147483647);
  return (
    <div className="mb-3 space-y-2">
      <label className="block text-xs text-zinc-400">Seed policy
        <select aria-label="Seed policy" value={policy} onChange={(e) => setPolicy(e.target.value)} className="mt-1 w-full rounded px-2 py-1.5">
          <option value="random">Random each generation</option><option value="fixed">Fixed for comparisons</option>
        </select>
      </label>
      {policy === "fixed" && <label className="block text-xs text-zinc-400">Seed
        <input aria-label="Fixed seed" type="number" min="0" max="2147483647" step="1" value={seed} onChange={(e) => setSeed(e.target.value)} className="mt-1 w-full rounded px-2 py-1.5" />
      </label>}
      <button type="button" onClick={() => save.mutate()} disabled={!valid || save.isPending} className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50">{save.isPending ? "Saving…" : "Save seed settings"}</button>
      {save.isSuccess && <p role="status" className="text-xs text-emerald-400">Saved for the next generation.</p>}
      {save.isError && <p role="alert" className="text-xs text-red-300">{toAIError(save.error).detail}</p>}
    </div>
  );
}
