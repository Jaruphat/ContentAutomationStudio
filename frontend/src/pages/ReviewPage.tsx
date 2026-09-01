/* ──────────────────────────────────────────────────────────────────────────
   ReviewPage -- Grid of shots with their takes. Approve / reject / regen.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
  Loader2,
  Filter,
  Image,
  AlertCircle,
} from "lucide-react";
import api from "../api/client";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import StatusBadge from "../components/StatusBadge";
import type { Take } from "../types";

type FilterMode = "all" | "Pending" | "Approved" | "Rejected";

// ── Take card ────────────────────────────────────────────────────────────

function TakeCard({
  take,
  projectId,
  isSelected,
  onSelect,
}: {
  take: Take;
  projectId: string;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const qc = useQueryClient();

  const approveMut = useMutation({
    mutationFn: () => api.review.approve(projectId, take.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["takes", projectId] }),
  });

  const rejectMut = useMutation({
    mutationFn: () => api.review.reject(projectId, take.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["takes", projectId] }),
  });

  const regenMut = useMutation({
    mutationFn: () => api.review.regenerate(projectId, take.shot_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["takes", projectId] });
      qc.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });

  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-lg border bg-zinc-900/70 transition-colors ${
        isSelected
          ? "border-indigo-500 ring-1 ring-indigo-500/30"
          : "border-zinc-800 hover:border-zinc-700"
      }`}
    >
      {/* Thumbnail placeholder */}
      <div className="flex h-36 items-center justify-center rounded-t-lg bg-zinc-800 text-zinc-600">
        {take.thumbnail_path ? (
          <span className="px-2 text-xs truncate">{take.thumbnail_path}</span>
        ) : (
          <Image size={28} />
        )}
      </div>

      <div className="p-3 space-y-2">
        {/* Meta row */}
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-zinc-500">
            {take.id.slice(0, 8)}
          </span>
          <StatusBadge status={take.review_status} />
        </div>

        {/* Info */}
        <div className="text-xs text-zinc-400 space-y-0.5">
          <div>
            Shot: <span className="text-zinc-300 font-mono">{take.shot_id.slice(0, 8)}</span>
          </div>
          {take.width > 0 && (
            <div>
              Res: {take.width}x{take.height}
            </div>
          )}
          {take.duration_sec > 0 && <div>Duration: {take.duration_sec}s</div>}
          {take.notes && (
            <div className="truncate text-zinc-500 italic">{take.notes}</div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-1.5 pt-1 border-t border-zinc-800">
          {take.review_status === "Pending" && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  approveMut.mutate();
                }}
                disabled={approveMut.isPending}
                className="flex flex-1 items-center justify-center gap-1 rounded-md bg-green-800/60 px-2 py-1 text-[11px] font-medium text-green-300 hover:bg-green-700/60 disabled:opacity-50"
              >
                {approveMut.isPending ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : (
                  <ThumbsUp size={11} />
                )}
                Approve
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  rejectMut.mutate();
                }}
                disabled={rejectMut.isPending}
                className="flex flex-1 items-center justify-center gap-1 rounded-md bg-red-900/50 px-2 py-1 text-[11px] font-medium text-red-300 hover:bg-red-800/50 disabled:opacity-50"
              >
                {rejectMut.isPending ? (
                  <Loader2 size={11} className="animate-spin" />
                ) : (
                  <ThumbsDown size={11} />
                )}
                Reject
              </button>
            </>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              regenMut.mutate();
            }}
            disabled={regenMut.isPending}
            className="flex items-center justify-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-[11px] font-medium text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
            title="Regenerate"
          >
            {regenMut.isPending ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <RefreshCw size={11} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// ReviewPage
// ══════════════════════════════════════════════════════════════════════════

export default function ReviewPage() {
  const { currentProjectId, selectedTakeId } = useAppState();
  const dispatch = useAppDispatch();
  const [filter, setFilter] = useState<FilterMode>("all");

  const takesQ = useQuery({
    queryKey: ["takes", currentProjectId],
    queryFn: () => api.review.listTakes(currentProjectId!),
    enabled: !!currentProjectId,
    refetchInterval: 3000,
  });

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <CheckCircle size={32} className="mb-3 text-zinc-600" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  const filtered =
    filter === "all"
      ? takesQ.data
      : takesQ.data?.filter((t) => t.review_status === filter);

  const pendingCount =
    takesQ.data?.filter((t) => t.review_status === "Pending").length ?? 0;
  const approvedCount =
    takesQ.data?.filter((t) => t.review_status === "Approved").length ?? 0;
  const rejectedCount =
    takesQ.data?.filter((t) => t.review_status === "Rejected").length ?? 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CheckCircle size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Review Takes</h1>
          {takesQ.data && (
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
              {takesQ.data.length} take{takesQ.data.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Filters + stats */}
      <div className="flex flex-wrap items-center gap-3">
        <Filter size={14} className="text-zinc-500" />
        {(
          [
            ["all", "All"],
            ["Pending", "Needs Review"],
            ["Approved", "Approved"],
            ["Rejected", "Rejected"],
          ] as [FilterMode, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filter === key
                ? "bg-indigo-600 text-white"
                : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {label}
          </button>
        ))}

        <div className="flex-1" />

        <div className="flex gap-3 text-xs">
          <span className="text-orange-400">Pending: {pendingCount}</span>
          <span className="text-green-400">Approved: {approvedCount}</span>
          <span className="text-red-400">Rejected: {rejectedCount}</span>
        </div>
      </div>

      {/* Loading */}
      {takesQ.isLoading && (
        <div className="flex items-center gap-2 py-12 text-zinc-500 justify-center">
          <Loader2 size={14} className="animate-spin" /> Loading takes...
        </div>
      )}

      {/* Error */}
      {takesQ.isError && (
        <div className="flex items-center gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} /> Failed to load takes.
        </div>
      )}

      {/* Empty */}
      {filtered && filtered.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Image size={28} className="mb-2 text-zinc-600" />
          <p className="text-sm text-zinc-500">
            {filter === "all"
              ? "No takes generated yet. Go to Generate to create them."
              : `No ${filter.toLowerCase()} takes found.`}
          </p>
        </div>
      )}

      {/* Grid */}
      {filtered && filtered.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {filtered.map((take) => (
            <TakeCard
              key={take.id}
              take={take}
              projectId={currentProjectId}
              isSelected={selectedTakeId === take.id}
              onSelect={() =>
                dispatch({ type: "SELECT_TAKE", id: take.id })
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
