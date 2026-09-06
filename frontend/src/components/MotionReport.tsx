import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Loader2 } from "lucide-react";
import api, { toAIError } from "../api/client";
import type { Take } from "../types";

interface Measurement {
  status: "measured" | "unavailable";
  mean_luma_change?: number;
  near_static_fraction?: number;
  sample_fps?: number;
  warnings?: string[];
  reason?: string;
}

export default function MotionReport({ take, projectId }: { take: Take; projectId: string }) {
  const qc = useQueryClient();
  const analysis = useMutation({
    mutationFn: () => api.review.analyze(take.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["takes", projectId] }),
  });
  if (take.duration_sec <= 0) return null;
  const report = (analysis.data?.provenance?.media_analysis ?? take.provenance?.media_analysis) as Measurement | undefined;
  const measured = report?.status === "measured";
  return (
    <div className="space-y-1.5 border-t border-zinc-800 pt-2 text-xs" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-medium text-zinc-300"><Activity size={13} /> Motion check</span>
        <button type="button" onClick={() => analysis.mutate()} disabled={analysis.isPending}
          className="rounded border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50">
          {analysis.isPending ? <Loader2 size={12} className="animate-spin" /> : measured ? "Measure again" : "Measure motion"}
        </button>
      </div>
      {measured ? (
        <p className="text-zinc-400">Visual change {report.mean_luma_change?.toFixed(2)} · {Math.round((report.near_static_fraction ?? 0) * 100)}% near-static samples</p>
      ) : <p className="text-zinc-500">{report?.reason ?? "This clip has not been measured."}</p>}
      {report?.warnings?.map((warning) => <p key={warning} className="text-amber-300">{warning}</p>)}
      {measured && <p className="text-[11px] text-zinc-500">Measured at {report.sample_fps} fps. Cuts and flicker also raise this value; watch the intended action before approving.</p>}
      {analysis.isError && <p role="alert" className="text-red-300">{toAIError(analysis.error).detail}</p>}
    </div>
  );
}
