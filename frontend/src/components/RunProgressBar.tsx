import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import api from "../api/client";
import type { GenerationJob } from "../types";

/**
 * A persistent line saying what is generating and how far it has got.
 *
 * A shot takes minutes on local hardware, and the stage a user is looking at
 * is usually not the Generate page. Without this, a slow render and a stuck
 * one look identical from anywhere else in the app.
 *
 * It reports only what the provider actually said. ComfyUI gives sampler steps
 * over its websocket; when a route offers nothing, this shows "Running" and no
 * percentage rather than a bar moving on a number nobody measured.
 */
export default function RunProgressBar({
  projectId,
  shotLabels = {},
  pollMs = 2000,
}: {
  projectId: string;
  /** Shot id to a human label, so the line names the shot and not a uuid. */
  shotLabels?: Record<string, string>;
  pollMs?: number;
}) {
  const { data } = useQuery({
    queryKey: ["jobs", projectId],
    queryFn: () => api.generation.listJobs(projectId),
    refetchInterval: pollMs,
  });

  const jobs: GenerationJob[] = data ?? [];
  const running = jobs.find((job) => job.status === "Running");
  const queued = jobs.filter((job) => job.status === "Queued").length;
  if (!running) return null;

  const fraction = Math.max(0, Math.min(1, running.progress ?? 0));
  const percent = Math.round(fraction * 100);
  const label = shotLabels[running.shot_id] || `Shot ${running.shot_id.slice(0, 8)}`;
  const stage = running.progress_stage || "";

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-1.5 text-xs"
    >
      <Loader2 size={13} className="shrink-0 animate-spin text-indigo-400" />
      <span className="shrink-0 font-medium text-zinc-200">{label}</span>
      <span className="min-w-0 flex-1 truncate text-zinc-500">
        {stage || "Running"}
      </span>
      {fraction > 0 && (
        <>
          <span
            aria-hidden="true"
            className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-zinc-800"
          >
            <span
              className="block h-full rounded-full bg-indigo-500 transition-[width]"
              style={{ width: `${percent}%` }}
            />
          </span>
          <span className="shrink-0 tabular-nums text-zinc-400">{percent}%</span>
        </>
      )}
      {queued > 0 && (
        <span className="shrink-0 text-zinc-500">{queued} queued</span>
      )}
    </div>
  );
}
