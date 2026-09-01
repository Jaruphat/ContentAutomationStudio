/* ──────────────────────────────────────────────────────────────────────────
   TimelinePage -- Timeline visualization of approved takes, build and
   render plan operations.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Film,
  Loader2,
  PlayCircle,
  ListOrdered,
  AlertCircle,
  Clock,
  ArrowRight,
  Terminal,
  AlertTriangle,
} from "lucide-react";
import api from "../api/client";
import { useAppState } from "../store/useProjectStore";
import type { RenderPlan, TimelineItem } from "../types";

// ── Timeline item row ────────────────────────────────────────────────────

function TimelineRow({ item, index }: { item: TimelineItem; index: number }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3">
      {/* Order indicator */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-zinc-300">
        {index + 1}
      </div>

      {/* Transition in */}
      <div className="flex items-center gap-1 text-[10px] text-zinc-500 min-w-[60px]">
        <ArrowRight size={10} />
        <span className="uppercase">{item.transition_in}</span>
      </div>

      {/* Main info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-300">
            Shot: <span className="font-mono">{item.shot_id?.slice(0, 8) ?? "--"}</span>
          </span>
          <span className="text-xs text-zinc-500">|</span>
          <span className="text-xs text-zinc-400">
            Take: <span className="font-mono">{item.take_id?.slice(0, 8) ?? "--"}</span>
          </span>
        </div>
      </div>

      {/* Duration */}
      <div className="flex items-center gap-1 text-xs text-zinc-400">
        <Clock size={12} />
        <span>{item.duration_sec.toFixed(1)}s</span>
      </div>

      {/* Time range */}
      <div className="text-[10px] text-zinc-500 min-w-[80px] text-right">
        {item.in_point_sec.toFixed(1)}s - {item.out_point_sec.toFixed(1)}s
      </div>

      {/* Transition out */}
      <div className="flex items-center gap-1 text-[10px] text-zinc-500 min-w-[60px]">
        <span className="uppercase">{item.transition_out}</span>
        <ArrowRight size={10} />
      </div>
    </div>
  );
}

// ── Render plan display ──────────────────────────────────────────────────

function RenderPlanPanel({ plan }: { plan: RenderPlan }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Terminal size={14} className="text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Render Plan</h3>
      </div>

      <div className="flex gap-4 text-xs">
        <span className="text-zinc-500">
          Total duration:{" "}
          <span className="text-zinc-300">
            {plan.total_duration_sec.toFixed(1)}s
          </span>
        </span>
        <span className="text-zinc-500">
          Segments:{" "}
          <span className="text-zinc-300">{plan.segments.length}</span>
        </span>
        <span className="text-zinc-500">
          FFmpeg:{" "}
          <span
            className={
              plan.ffmpeg_available ? "text-green-400" : "text-red-400"
            }
          >
            {plan.ffmpeg_available ? "Available" : "Not found"}
          </span>
        </span>
      </div>

      {!plan.ffmpeg_available && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-900/20 border border-yellow-800/50 px-3 py-2 text-xs text-yellow-300">
          <AlertTriangle size={13} />
          FFmpeg is not installed or not on PATH. Render commands are shown but cannot execute without real media assets.
        </div>
      )}

      {plan.commands.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            FFmpeg Commands
          </h4>
          <div className="max-h-48 overflow-y-auto rounded-md bg-zinc-950 p-3">
            {plan.commands.map((cmd, i) => (
              <pre
                key={i}
                className="text-[11px] text-zinc-400 font-mono whitespace-pre-wrap mb-2 last:mb-0"
              >
                $ {cmd}
              </pre>
            ))}
          </div>
        </div>
      )}

      {plan.commands.length === 0 && plan.segments.length === 0 && (
        <p className="text-xs text-zinc-500 italic">
          No segments available. Build the timeline first with approved takes.
        </p>
      )}

      {plan.segments.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Segments
          </h4>
          <div className="space-y-1">
            {plan.segments.map((seg, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-md bg-zinc-800/50 px-3 py-1.5 text-xs"
              >
                <span className="font-mono text-zinc-500">#{seg.order}</span>
                <span className="text-zinc-300 truncate flex-1">
                  {seg.file_path || "no file"}
                </span>
                <span className="text-zinc-400">{seg.duration_sec}s</span>
                <span className="text-zinc-500">
                  {seg.transition_in} / {seg.transition_out}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// TimelinePage
// ══════════════════════════════════════════════════════════════════════════

export default function TimelinePage() {
  const { currentProjectId } = useAppState();
  const qc = useQueryClient();
  const [renderPlan, setRenderPlan] = useState<RenderPlan | null>(null);

  const timelineQ = useQuery({
    queryKey: ["timeline", currentProjectId],
    queryFn: () => api.timeline.get(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const buildMut = useMutation({
    mutationFn: () => api.timeline.build(currentProjectId!),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["timeline", currentProjectId] }),
  });

  const renderPlanMut = useMutation({
    mutationFn: () => api.timeline.renderPlan(currentProjectId!),
    onSuccess: (data) => setRenderPlan(data),
  });

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <Film size={32} className="mb-3 text-zinc-600" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  const totalDuration =
    timelineQ.data?.reduce((sum, item) => sum + item.duration_sec, 0) ?? 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Film size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Timeline</h1>
          {timelineQ.data && timelineQ.data.length > 0 && (
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
              {timelineQ.data.length} item{timelineQ.data.length !== 1 ? "s" : ""} -- {totalDuration.toFixed(1)}s
            </span>
          )}
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => buildMut.mutate()}
            disabled={buildMut.isPending}
            className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {buildMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <ListOrdered size={14} />
            )}
            Build Timeline
          </button>
          <button
            onClick={() => renderPlanMut.mutate()}
            disabled={renderPlanMut.isPending}
            className="flex items-center gap-1.5 rounded-md border border-zinc-700 px-4 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {renderPlanMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <PlayCircle size={14} />
            )}
            Render Plan
          </button>
        </div>
      </div>

      {/* Errors */}
      {buildMut.isError && (
        <div className="flex items-center gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} /> Failed to build timeline.
        </div>
      )}

      {/* Loading */}
      {timelineQ.isLoading && (
        <div className="flex items-center gap-2 py-12 text-zinc-500 justify-center">
          <Loader2 size={14} className="animate-spin" /> Loading timeline...
        </div>
      )}

      {/* Empty */}
      {timelineQ.data && timelineQ.data.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Film size={28} className="mb-2 text-zinc-600" />
          <p className="text-sm text-zinc-500">
            No timeline items yet. Approve takes in Review, then click "Build Timeline"
            to assemble the sequence.
          </p>
        </div>
      )}

      {/* Timeline list */}
      {timelineQ.data && timelineQ.data.length > 0 && (
        <div className="space-y-2">
          {timelineQ.data
            .sort((a, b) => a.order - b.order)
            .map((item, i) => (
              <TimelineRow key={item.id} item={item} index={i} />
            ))}
        </div>
      )}

      {/* Render plan */}
      {renderPlan && <RenderPlanPanel plan={renderPlan} />}
    </div>
  );
}
