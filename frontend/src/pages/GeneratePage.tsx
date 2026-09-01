/* ──────────────────────────────────────────────────────────────────────────
   GeneratePage -- Preflight validation, workflow selection, generation
   queue management, and job status monitoring.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Zap,
  Shield,
  CheckCircle2,
  XCircle,
  Loader2,
  Play,
  Pause,
  RefreshCw,
  Ban,
  Clock,
  AlertCircle,
} from "lucide-react";
import api from "../api/client";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import StatusBadge from "../components/StatusBadge";
import type { PreflightResult, GenerationJob } from "../types";

// ── Preflight panel ──────────────────────────────────────────────────────

function PreflightPanel({
  result,
  onRun,
  running,
}: {
  result: PreflightResult | null;
  onRun: () => void;
  running: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-zinc-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Preflight Validation
          </h2>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        >
          {running ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Shield size={12} />
          )}
          Run Preflight
        </button>
      </div>

      {!result && (
        <p className="text-xs text-zinc-500 italic">
          Run preflight validation to check if the project is ready for generation.
        </p>
      )}

      {result && (
        <div className="space-y-2">
          <div
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
              result.ready
                ? "bg-green-900/30 text-green-300"
                : "bg-red-900/30 text-red-300"
            }`}
          >
            {result.ready ? (
              <CheckCircle2 size={14} />
            ) : (
              <XCircle size={14} />
            )}
            {result.ready ? "All checks passed" : "Some checks failed"}
          </div>

          <div className="space-y-1">
            {result.checks.map((check, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-md px-3 py-1.5 text-xs"
              >
                {check.passed ? (
                  <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-green-500" />
                ) : (
                  <XCircle size={12} className="mt-0.5 shrink-0 text-red-500" />
                )}
                <div>
                  <span className="font-medium text-zinc-300">
                    {check.label}
                  </span>
                  <span className="ml-1 text-zinc-500">{check.category}</span>
                  <p className="mt-0.5 text-zinc-400">{check.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Job row ──────────────────────────────────────────────────────────────

function JobRow({
  job,
  projectId,
}: {
  job: GenerationJob;
  projectId: string;
}) {
  const qc = useQueryClient();

  const cancelMut = useMutation({
    mutationFn: () => api.generation.cancelJob(projectId, job.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["jobs", projectId] }),
  });

  const retryMut = useMutation({
    mutationFn: () => api.generation.retryJob(projectId, job.id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["jobs", projectId] }),
  });

  const statusIcon = () => {
    switch (job.status) {
      case "Queued":
        return <Clock size={13} className="text-blue-400" />;
      case "Running":
        return <Loader2 size={13} className="animate-spin text-yellow-400" />;
      case "Completed":
        return <CheckCircle2 size={13} className="text-green-400" />;
      case "Failed":
        return <XCircle size={13} className="text-red-400" />;
      case "Cancelled":
        return <Ban size={13} className="text-zinc-400" />;
      default:
        return null;
    }
  };

  return (
    <tr className="border-t border-zinc-800 hover:bg-zinc-800/30">
      <td className="px-3 py-2 text-xs text-zinc-500 font-mono">
        {job.id.slice(0, 8)}...
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500 font-mono">
        {job.shot_id.slice(0, 8)}...
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-1.5">
          {statusIcon()}
          <StatusBadge status={job.status} />
        </div>
      </td>
      <td className="px-3 py-2 text-xs text-zinc-400">{job.attempts}</td>
      <td className="px-3 py-2 text-xs text-zinc-500">
        {job.seed !== null ? job.seed : "--"}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">
        {job.created_at
          ? new Date(job.created_at).toLocaleTimeString()
          : "--"}
      </td>
      <td className="px-3 py-2">
        {job.error_message && (
          <span className="text-xs text-red-400 truncate max-w-[150px] inline-block">
            {job.error_message}
          </span>
        )}
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-1">
          {(job.status === "Queued" || job.status === "Running") && (
            <button
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
              className="rounded p-1 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
              title="Cancel"
            >
              <Ban size={13} />
            </button>
          )}
          {(job.status === "Failed" || job.status === "Cancelled") && (
            <button
              onClick={() => retryMut.mutate()}
              disabled={retryMut.isPending}
              className="rounded p-1 text-zinc-500 hover:bg-blue-900/50 hover:text-blue-400"
              title="Retry"
            >
              <RefreshCw size={13} />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// GeneratePage
// ══════════════════════════════════════════════════════════════════════════

export default function GeneratePage() {
  const { currentProjectId, queuePaused } = useAppState();
  const dispatch = useAppDispatch();
  const qc = useQueryClient();
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>("");

  // ── Queries ────────────────────────────────────────────────────────────
  const workflowsQ = useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows.list,
  });

  const jobsQ = useQuery({
    queryKey: ["jobs", currentProjectId],
    queryFn: () => api.generation.listJobs(currentProjectId!),
    enabled: !!currentProjectId,
    refetchInterval: 2000,
  });

  // ── Mutations ──────────────────────────────────────────────────────────
  const preflightMut = useMutation({
    mutationFn: () => api.generation.preflight(currentProjectId!),
    onSuccess: (data) => setPreflight(data),
  });

  const generateMut = useMutation({
    mutationFn: () => api.generation.start(currentProjectId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs", currentProjectId] });
    },
  });

  const pauseMut = useMutation({
    mutationFn: () => api.generation.pauseQueue(currentProjectId!),
    onSuccess: () =>
      dispatch({ type: "SET_QUEUE_PAUSED", paused: true }),
  });

  const resumeMut = useMutation({
    mutationFn: () => api.generation.resumeQueue(currentProjectId!),
    onSuccess: () =>
      dispatch({ type: "SET_QUEUE_PAUSED", paused: false }),
  });

  // ── No project ─────────────────────────────────────────────────────────
  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <Zap size={32} className="mb-3 text-zinc-600" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  const queuedCount = jobsQ.data?.filter((j) => j.status === "Queued").length ?? 0;
  const runningCount = jobsQ.data?.filter((j) => j.status === "Running").length ?? 0;
  const completedCount = jobsQ.data?.filter((j) => j.status === "Completed").length ?? 0;
  const failedCount = jobsQ.data?.filter((j) => j.status === "Failed").length ?? 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Zap size={20} className="text-indigo-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Generate</h1>
      </div>

      {/* Preflight */}
      <PreflightPanel
        result={preflight}
        onRun={() => preflightMut.mutate()}
        running={preflightMut.isPending}
      />

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3">
        {/* Workflow selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-400">Workflow:</span>
          <select
            value={selectedWorkflowId}
            onChange={(e) => setSelectedWorkflowId(e.target.value)}
            className="rounded-md px-2 py-1 text-xs min-w-[180px]"
          >
            <option value="">-- Default --</option>
            {workflowsQ.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.purpose})
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1" />

        {/* Queue controls */}
        {queuePaused ? (
          <button
            onClick={() => resumeMut.mutate()}
            disabled={resumeMut.isPending}
            className="flex items-center gap-1.5 rounded-md bg-green-700 px-3 py-1.5 text-xs font-medium text-green-100 hover:bg-green-600 disabled:opacity-50"
          >
            <Play size={12} /> Resume Queue
          </button>
        ) : (
          <button
            onClick={() => pauseMut.mutate()}
            disabled={pauseMut.isPending}
            className="flex items-center gap-1.5 rounded-md border border-yellow-700 px-3 py-1.5 text-xs font-medium text-yellow-300 hover:bg-yellow-900/30 disabled:opacity-50"
          >
            <Pause size={12} /> Pause Queue
          </button>
        )}

        {/* Generate button */}
        <button
          onClick={() => {
            if (
              window.confirm(
                "Start generation for all Ready shots in this project?",
              )
            ) {
              generateMut.mutate();
            }
          }}
          disabled={generateMut.isPending}
          className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {generateMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Zap size={14} />
          )}
          Generate
        </button>
      </div>

      {generateMut.isError && (
        <div className="flex items-center gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} />
          {(generateMut.error as Error).message || "Generation failed to start."}
        </div>
      )}

      {/* Stats bar */}
      {jobsQ.data && jobsQ.data.length > 0 && (
        <div className="flex gap-4 text-xs">
          <span className="text-zinc-500">
            Total: <span className="text-zinc-300">{jobsQ.data.length}</span>
          </span>
          <span className="text-blue-400">Queued: {queuedCount}</span>
          <span className="text-yellow-400">Running: {runningCount}</span>
          <span className="text-green-400">Completed: {completedCount}</span>
          <span className="text-red-400">Failed: {failedCount}</span>
        </div>
      )}

      {/* Jobs table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 overflow-hidden">
        <div className="border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-200">Job Queue</h2>
        </div>

        {jobsQ.isLoading && (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-zinc-500 justify-center">
            <Loader2 size={14} className="animate-spin" /> Loading jobs...
          </div>
        )}

        {jobsQ.data && jobsQ.data.length === 0 && (
          <div className="flex flex-col items-center py-12 text-center">
            <Clock size={24} className="mb-2 text-zinc-600" />
            <p className="text-sm text-zinc-500">
              No generation jobs yet. Run preflight and click Generate to start.
            </p>
          </div>
        )}

        {jobsQ.data && jobsQ.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="px-3 py-2">Job ID</th>
                  <th className="px-3 py-2">Shot</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Attempts</th>
                  <th className="px-3 py-2">Seed</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Error</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {jobsQ.data.map((job) => (
                  <JobRow key={job.id} job={job} projectId={currentProjectId} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
