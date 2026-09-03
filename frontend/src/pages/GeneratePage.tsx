/* ──────────────────────────────────────────────────────────────────────────
   GeneratePage -- readiness, what a run will cost, and the job queue.

   The page follows the decision a user actually makes: is the project ready,
   what will pressing Generate run and charge, and then what happened. Workflow
   node mappings answer none of those questions -- they are setup diagnostics
   for whoever is wiring ComfyUI up -- so they live behind a disclosure instead
   of dominating the screen.

   The price shown before a run and the price the queue then incurs come from
   the same backend planner, so the two cannot drift apart.
   ────────────────────────────────────────────────────────────────────────── */

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
  AlertTriangle,
  Wrench,
} from "lucide-react";
import api, { toAIError } from "../api/client";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import StatusBadge from "../components/StatusBadge";
import CostConfirmDialog from "../components/CostConfirmDialog";
import type {
  GenerationEstimate,
  GenerationJob,
  GenerationRun,
  GenerationRunJob,
  MediaHealthResponse,
  MediaProviderCatalogue,
  MediaProviderId,
  PreflightResult,
  Workflow,
} from "../types";

function formatUsd(amount: number): string {
  return amount.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

/** The deterministic mock derives its prompt id from the job id. */
function isMockJob(job: GenerationJob): boolean {
  return (job.comfyui_prompt_id ?? "").startsWith("mock-");
}

type RunTab = "current" | "failed" | "completed" | "history";

function RunJobCard({ job }: { job: GenerationRunJob }) {
  return (
    <article className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/60">
      <div className="aspect-video bg-zinc-950">
        {job.thumbnail_url ? (
          <img
            src={job.thumbnail_url}
            alt={`Preview for ${job.shot_name}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            No preview
          </div>
        )}
      </div>
      <div className="space-y-2 p-3">
        <p className="text-xs text-zinc-500">{job.scene_name}</p>
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-sm font-medium text-zinc-200">{job.shot_name}</h4>
          <StatusBadge status={job.status} />
        </div>
        {job.error_message && <p className="text-xs text-red-400">{job.error_message}</p>}
      </div>
    </article>
  );
}

function RunSection({
  run,
  jobs = run.jobs,
}: {
  run: GenerationRun;
  jobs?: GenerationRunJob[];
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-zinc-100">{run.label}</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {run.completed} completed · {run.failed} failed · {run.cancelled} cancelled ·{" "}
            {run.queued} queued · {run.running} running · of {run.total_jobs}
          </p>
        </div>
        {run.terminal && run.ready_for_review && run.pending_take_count > 0 && (
          <Link
            to={`/review?run=${encodeURIComponent(run.id)}`}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Go to Review
          </Link>
        )}
      </div>
      {jobs.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <RunJobCard key={job.job_id} job={job} />
          ))}
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-zinc-500">No jobs in this view.</p>
      )}
    </section>
  );
}

type Tone = "ok" | "warn" | "bad" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "border-green-800/60 bg-green-900/30 text-green-300",
  warn: "border-amber-800/60 bg-amber-900/30 text-amber-300",
  bad: "border-red-800/60 bg-red-900/30 text-red-300",
  muted: "border-zinc-700 bg-zinc-800 text-zinc-300",
};

function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

function RuntimeBanner({
  health,
  loading,
}: {
  health: MediaHealthResponse | undefined;
  loading: boolean;
}) {
  const comfyui = health?.providers.find((provider) => provider.id === "comfyui");
  const mode = loading
    ? { text: "CHECKING · ComfyUI runtime", tone: "muted" as Tone }
    : comfyui?.mock
      ? { text: "SIMULATION · Mock", tone: "warn" as Tone }
      : comfyui?.online
        ? { text: "REAL · ComfyUI connected", tone: "ok" as Tone }
        : { text: "OFFLINE · ComfyUI unavailable", tone: "bad" as Tone };

  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm font-semibold ${TONE_CLASS[mode.tone]}`}
    >
      {mode.tone === "ok" ? (
        <CheckCircle2 size={16} />
      ) : mode.tone === "muted" ? (
        <Loader2 size={16} className="animate-spin" />
      ) : (
        <AlertTriangle size={16} />
      )}
      {mode.text}
    </div>
  );
}

// ── Top summary ──────────────────────────────────────────────────────────

/**
 * Readiness, blockers, warnings and provider state in one glance.
 *
 * Repeated shot issues are grouped by their text: nine shots missing a prompt
 * is one thing to fix, not nine.
 */
function ReadinessSummary({
  preflight,
  loading,
  error,
  onRerun,
  catalogue,
  mediaHealth,
  unrunnableWorkflows,
}: {
  preflight: PreflightResult | undefined;
  loading: boolean;
  error: string | null;
  onRerun: () => void;
  catalogue: MediaProviderCatalogue | undefined;
  mediaHealth: MediaHealthResponse | undefined;
  unrunnableWorkflows: Workflow[];
}) {
  const blockerGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const issue of preflight?.issues ?? []) {
      for (const text of issue.issues) {
        counts.set(text, (counts.get(text) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [preflight]);

  const blockedShots = preflight?.issues.length ?? 0;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-zinc-400" />
          <h2 className="text-sm font-semibold text-zinc-200">
            Readiness
          </h2>
        </div>
        <button
          onClick={onRerun}
          disabled={loading}
          className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-700 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Shield size={12} />
          )}
          Run preflight
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-3 py-2 text-sm text-red-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!preflight && !error && (
        <p className="text-sm text-zinc-500">
          {loading
            ? "Checking every shot, workflow and provider..."
            : "Run preflight to check whether this project can generate."}
        </p>
      )}

      {preflight && (
        <div className="space-y-3">
          <div
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
              preflight.ready
                ? "bg-green-900/30 text-green-300"
                : "bg-red-900/30 text-red-300"
            }`}
          >
            {preflight.ready ? (
              <CheckCircle2 size={14} />
            ) : (
              <XCircle size={14} />
            )}
            {preflight.ready
              ? `All ${preflight.total_shots} shot(s) ready to generate`
              : `${preflight.ready_shots} of ${preflight.total_shots} shot(s) ready`}
          </div>

          {/* Counters: the three numbers that decide whether to press Generate */}
          <div className="flex flex-wrap gap-2">
            <Chip tone={blockedShots > 0 ? "bad" : "ok"}>
              {blockedShots} blocking issue{blockedShots === 1 ? "" : "s"}
            </Chip>
            <Chip tone={preflight.warnings.length > 0 ? "warn" : "muted"}>
              {preflight.warnings.length} warning
              {preflight.warnings.length === 1 ? "" : "s"}
            </Chip>
            {unrunnableWorkflows.length > 0 && (
              <Chip tone="warn">
                {unrunnableWorkflows.length} workflow
                {unrunnableWorkflows.length === 1 ? "" : "s"} not API-format
              </Chip>
            )}
          </div>

          {/* Providers and whether any of them is a stand-in */}
          <div className="flex flex-wrap gap-2">
            {catalogue?.providers.map((provider) => {
              const live = mediaHealth?.providers.find(
                (p) => p.id === provider.id,
              );
              const role =
                provider.id === catalogue.video_provider_id
                  ? provider.id === catalogue.default_image_provider_id
                    ? "image + video"
                    : "video"
                  : "image";
              const tone: Tone = !provider.configured
                ? "muted"
                : live?.mock
                  ? "warn"
                  : live?.online
                    ? "ok"
                    : "bad";
              return (
                <Chip key={provider.id} tone={tone}>
                  {provider.label} ({role}):{" "}
                  {!provider.configured
                    ? `set ${provider.api_key_env} to enable`
                    : live?.mock
                      ? "deterministic mock, not a real render"
                      : live?.online
                        ? "online"
                        : "offline"}
                </Chip>
              );
            })}
            {preflight.comfyui_mock && !mediaHealth && (
              <Chip tone="warn">
                ComfyUI is mocked: output is deterministic placeholder media
              </Chip>
            )}
          </div>

          {preflight.warnings.map((warning) => (
            <div
              key={warning}
              className="flex items-start gap-2 rounded-md border border-amber-800/50 bg-amber-900/20 px-3 py-2 text-xs text-amber-300"
            >
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>{warning}</span>
            </div>
          ))}

          {/* One line per distinct problem, with how many shots have it. */}
          {blockerGroups.length > 0 && (
            <div className="space-y-1">
              <h3 className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                Fix before generating
              </h3>
              {blockerGroups.map(([text, count]) => (
                <div
                  key={text}
                  className="flex items-start gap-2 rounded-md bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-300"
                >
                  <XCircle size={12} className="mt-0.5 shrink-0 text-red-500" />
                  <span className="flex-1">{text}</span>
                  <span className="shrink-0 rounded bg-zinc-700 px-1.5 py-0.5 text-[11px] text-zinc-200">
                    {count} shot{count === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const MISSING_WORKFLOW_BLOCKER =
  "No workflow assigned (shot or project default)";

function WorkflowRecovery({
  imageWorkflows,
  videoWorkflows,
  imageWorkflowId,
  videoWorkflowId,
  onImageWorkflowChange,
  onVideoWorkflowChange,
  onApply,
  applying,
  error,
}: {
  imageWorkflows: Workflow[];
  videoWorkflows: Workflow[];
  imageWorkflowId: string;
  videoWorkflowId: string;
  onImageWorkflowChange: (id: string) => void;
  onVideoWorkflowChange: (id: string) => void;
  onApply: () => void;
  applying: boolean;
  error: string | null;
}) {
  const canApply = !!imageWorkflowId && !!videoWorkflowId && !applying;

  return (
    <section className="rounded-lg border border-indigo-700/60 bg-indigo-950/30 p-4">
      <div className="flex items-start gap-2">
        <Wrench size={16} className="mt-0.5 shrink-0 text-indigo-300" />
        <div>
          <h2 className="text-sm font-semibold text-indigo-100">
            Assign project workflow defaults
          </h2>
          <p className="mt-1 text-xs text-indigo-200/70">
            Choose runnable API-format workflows to clear the missing-workflow
            blocker for shots without their own override.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="space-y-1 text-xs font-medium text-zinc-300">
          <span>Default image workflow</span>
          <select
            value={imageWorkflowId}
            onChange={(event) => onImageWorkflowChange(event.target.value)}
            className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm text-zinc-100"
          >
            <option value="">Select an image workflow</option>
            {imageWorkflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
          {imageWorkflows.length === 0 && (
            <span className="block font-normal text-amber-300">
              No valid API-format image workflow is registered.
            </span>
          )}
        </label>

        <label className="space-y-1 text-xs font-medium text-zinc-300">
          <span>Default video workflow</span>
          <select
            value={videoWorkflowId}
            onChange={(event) => onVideoWorkflowChange(event.target.value)}
            className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm text-zinc-100"
          >
            <option value="">Select a video workflow</option>
            {videoWorkflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
          {videoWorkflows.length === 0 && (
            <span className="block font-normal text-amber-300">
              No valid API-format video workflow is registered.
            </span>
          )}
        </label>
      </div>

      {error && <p className="mt-3 text-xs text-red-300">{error}</p>}

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onApply}
          disabled={!canApply}
          className="flex h-9 items-center gap-1.5 rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {applying && <Loader2 size={13} className="animate-spin" />}
          Apply workflows
        </button>
      </div>
    </section>
  );
}

// ── Cost / run panel ─────────────────────────────────────────────────────

function RunPanel({
  estimate,
  loading,
  error,
  providerLabel,
  onGenerate,
  generating,
  generateError,
  queuePaused,
  showQueueControl,
  onPause,
  onResume,
  queueBusy,
  simulationRequired,
  simulationAcknowledged,
  onSimulationAcknowledged,
  comfyuiRuntimeUnavailable,
  preflightReady,
}: {
  estimate: GenerationEstimate | undefined;
  loading: boolean;
  error: string | null;
  providerLabel: (id: MediaProviderId) => string;
  onGenerate: () => void;
  generating: boolean;
  generateError: string | null;
  queuePaused: boolean;
  showQueueControl: boolean;
  onPause: () => void;
  onResume: () => void;
  queueBusy: boolean;
  simulationRequired: boolean;
  simulationAcknowledged: boolean;
  onSimulationAcknowledged: (checked: boolean) => void;
  comfyuiRuntimeUnavailable: boolean;
  preflightReady: boolean;
}) {
  const nothingToRun = !!estimate && estimate.shot_count === 0;
  const paid = !!estimate?.requires_confirmation;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Zap size={16} className="text-zinc-400" />
        <h2 className="text-sm font-semibold text-zinc-200">
          This run
        </h2>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 size={14} className="animate-spin" />
          Working out what Generate would run...
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-3 py-2 text-sm text-red-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {estimate && (
        <div className="space-y-3">
          {nothingToRun ? (
            <p className="text-sm text-zinc-500">
              No shots are ready to generate. Clear the blocking issues above
              first.
            </p>
          ) : (
            <>
              {/* Per-provider breakdown: who runs what, and for how much. */}
              <div className="overflow-hidden rounded-md border border-zinc-800">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-zinc-800 text-[11px] uppercase tracking-wider text-zinc-500">
                      <th className="px-3 py-2">Provider</th>
                      <th className="px-3 py-2">Model</th>
                      <th className="px-3 py-2">Shots</th>
                      <th className="px-3 py-2">Estimated cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {estimate.providers.map((entry) => (
                      <tr
                        key={entry.provider_id}
                        className="border-t border-zinc-800 text-xs"
                      >
                        <td className="px-3 py-2 text-zinc-200">
                          {providerLabel(entry.provider_id)}
                          {!entry.configured && (
                            <span className="ml-1.5 text-red-400">
                              not configured here
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-400">
                          {entry.model}
                        </td>
                        <td className="px-3 py-2 text-zinc-300">
                          {entry.shot_count}
                        </td>
                        <td className="px-3 py-2 text-zinc-300">
                          {!entry.paid
                            ? "No API charge (local)"
                            : entry.estimated_cost_usd !== null
                              ? formatUsd(entry.estimated_cost_usd)
                              : "No published rate"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* The cost basis is only shown where there is a cost. */}
              {paid ? (
                <div className="rounded-md border border-amber-800/60 bg-amber-900/20 px-3 py-2">
                  <p className="text-sm font-medium text-amber-200">
                    {estimate.estimated_cost_usd !== null
                      ? `Estimated total ${formatUsd(estimate.estimated_cost_usd)} for ${estimate.paid_shot_count} paid shot(s)`
                      : `${estimate.paid_shot_count} paid shot(s); no published rate to total`}
                  </p>
                  {estimate.providers
                    .filter((p) => p.paid && p.cost_basis)
                    .map((p) => (
                      <p
                        key={p.provider_id}
                        className="mt-1 text-xs text-amber-100/80"
                      >
                        {p.cost_basis}
                      </p>
                    ))}
                  {estimate.unpriced_paid_shots > 0 && (
                    <p className="mt-1 text-xs text-amber-100/80">
                      {estimate.unpriced_paid_shots} paid shot(s) have no
                      published rate, so the total above is not the whole
                      charge.
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-zinc-400">
                  {estimate.shot_count} shot(s) run locally. No vendor charge,
                  so no confirmation is required.
                </p>
              )}

              {estimate.blockers.map((blocker) => (
                <div
                  key={blocker}
                  className="flex items-start gap-2 rounded-md border border-red-800/60 bg-red-900/20 px-3 py-2 text-xs text-red-300"
                >
                  <AlertCircle size={12} className="mt-0.5 shrink-0" />
                  <span>{blocker}</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {generateError && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-3 py-2 text-sm text-red-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{generateError}</span>
        </div>
      )}

      {simulationRequired && (
        <label className="mt-3 flex items-start gap-2 rounded-md border border-amber-800/60 bg-amber-900/20 px-3 py-2 text-sm text-amber-200">
          <input
            type="checkbox"
            checked={simulationAcknowledged}
            onChange={(event) => onSimulationAcknowledged(event.target.checked)}
            className="mt-0.5"
          />
          <span>
            I intend to generate placeholder media in Simulation Mode. This is
            not a real ComfyUI render.
          </span>
        </label>
      )}

      {comfyuiRuntimeUnavailable && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-red-800/60 bg-red-900/20 px-3 py-2 text-sm text-red-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          Live ComfyUI runtime is not available. Generation remains disabled
          until health confirms either a real connection or Simulation Mode.
        </div>
      )}

      {/* Controls */}
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-zinc-800 pt-3">
        {showQueueControl && (queuePaused ? (
          <button
            onClick={onResume}
            disabled={queueBusy}
            className="flex h-9 items-center gap-1.5 rounded-md bg-green-700 px-3.5 text-xs font-medium text-green-100 hover:bg-green-600 disabled:opacity-50"
          >
            <Play size={13} /> Resume queue
          </button>
        ) : (
          <button
            onClick={onPause}
            disabled={queueBusy}
            className="flex h-9 items-center gap-1.5 rounded-md border border-yellow-700 px-3.5 text-xs font-medium text-yellow-300 hover:bg-yellow-900/30 disabled:opacity-50"
          >
            <Pause size={13} /> Pause queue
          </button>
        ))}

        <div className="flex-1" />

        <button
          data-testid="generate-button"
          onClick={onGenerate}
          disabled={
            generating ||
            loading ||
            !estimate ||
            nothingToRun ||
            !preflightReady ||
            comfyuiRuntimeUnavailable ||
            (simulationRequired && !simulationAcknowledged)
          }
          className="flex h-9 items-center gap-1.5 rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {generating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Zap size={14} />
          )}
          {paid ? "Generate (review cost)" : "Generate"}
        </button>
      </div>
    </div>
  );
}

// ── Workflow format diagnostics ──────────────────────────────────────────

/**
 * Explains why a registered workflow cannot drive real generation.
 *
 * A ComfyUI editor graph is the file most people have to hand, and it is
 * indistinguishable from an API export by name alone, so the reason is spelled
 * out here rather than surfacing only as a failed job.
 */
function WorkflowFormatPanel({ workflow }: { workflow: Workflow }) {
  const analysisQ = useQuery({
    queryKey: ["workflow-analysis", workflow.id],
    queryFn: () => api.workflows.analysis(workflow.id),
  });

  const analysis = analysisQ.data;

  return (
    <div className="space-y-3 rounded-lg border border-amber-800/60 bg-amber-900/15 p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle size={14} className="text-amber-400" />
        <h3 className="text-sm font-semibold text-amber-200">
          {workflow.name} is {workflow.source_format}-format and cannot run
        </h3>
      </div>

      <p className="text-xs text-amber-100/80">
        ComfyUI only executes API-format JSON. Open this workflow in ComfyUI and
        choose <span className="font-medium">Workflow &rarr; Export (API)</span>,
        then import that file here and map its nodes.
      </p>

      {analysisQ.isLoading && (
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <Loader2 size={12} className="animate-spin" /> Analysing workflow...
        </div>
      )}

      {analysisQ.isError && (
        <p className="text-xs text-red-300">
          {toAIError(analysisQ.error).detail}
        </p>
      )}

      {analysis && (
        <div className="space-y-3">
          {/* Dependency check against the live instance */}
          <div className="rounded-md bg-zinc-950/60 px-3 py-2 text-xs">
            <span className="text-zinc-400">Dependencies: </span>
            {analysis.dependencies.checked ? (
              <span
                className={
                  analysis.dependencies.satisfied
                    ? "text-green-400"
                    : "text-red-400"
                }
              >
                {analysis.dependencies.summary}
              </span>
            ) : (
              <span className="text-zinc-500">
                {analysis.dependencies.reason}
              </span>
            )}
          </div>

          {analysis.dependencies.models_missing.length > 0 && (
            <div className="text-xs text-red-300">
              Missing models: {analysis.dependencies.models_missing.join(", ")}
            </div>
          )}

          {/* What the mapping will look like after export */}
          {analysis.mapping_candidates.length > 0 && (
            <div className="space-y-1">
              <h4 className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                Candidate mappings (confirm after API export)
              </h4>
              {analysis.mapping_candidates.map((c) => (
                <div
                  key={c.logical_field}
                  className="flex items-center gap-2 rounded-md bg-zinc-800/50 px-3 py-1 text-xs"
                >
                  <span className="min-w-[120px] font-mono text-indigo-300">
                    {c.logical_field}
                  </span>
                  <span className="text-zinc-500">&rarr;</span>
                  <span className="truncate text-zinc-300">
                    {c.node_class}.{c.input_name}
                  </span>
                  {!c.exposed && (
                    <span className="ml-auto shrink-0 rounded bg-zinc-700 px-1.5 py-0.5 text-[11px] text-zinc-300">
                      inside subgraph
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {analysis.unmapped_logical_fields.length > 0 && (
            <div className="text-xs text-zinc-500">
              No candidate found for:{" "}
              {analysis.unmapped_logical_fields.join(", ")}
            </div>
          )}

          {analysis.warnings.map((w) => (
            <p key={w} className="text-xs text-amber-300/80">
              {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Job row ──────────────────────────────────────────────────────────────

function JobRow({
  job,
  projectId,
  providerLabel,
}: {
  job: GenerationJob;
  projectId: string;
  providerLabel: (id: MediaProviderId) => string;
}) {
  const qc = useQueryClient();

  const cancelMut = useMutation({
    mutationFn: () => api.generation.cancelJob(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", projectId] }),
  });

  const retryMut = useMutation({
    mutationFn: () => api.generation.retryJob(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", projectId] }),
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

  const actionError = cancelMut.isError
    ? toAIError(cancelMut.error).detail
    : retryMut.isError
      ? toAIError(retryMut.error).detail
      : null;

  return (
    <tr className="border-t border-zinc-800 hover:bg-zinc-800/30">
      <td className="px-3 py-2 font-mono text-xs text-zinc-500">
        {job.shot_id.slice(0, 8)}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-300">
        <div>{providerLabel(job.media_provider_id)}</div>
        {job.media_provider_id === "openai" ? (
          <div className="mt-1 text-[11px] font-medium text-sky-300">
            {providerLabel("openai")} · {job.media_model}
          </div>
        ) : isMockJob(job) ? (
          <div className="mt-1 text-[11px] font-medium text-amber-300">
            SIMULATION · Mock
          </div>
        ) : job.comfyui_prompt_id ? (
          <div className="mt-1 font-mono text-[11px] text-green-300">
            ComfyUI prompt {job.comfyui_prompt_id}
          </div>
        ) : (
          <div className="mt-1 text-[11px] text-zinc-500">
            ComfyUI prompt pending
          </div>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-400">
        {job.media_model || "--"}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-1.5">
          {statusIcon()}
          <StatusBadge status={job.status} />
        </div>
      </td>
      <td className="px-3 py-2 text-xs text-zinc-400">{job.attempts}</td>
      <td className="px-3 py-2 text-xs text-zinc-300">
        {job.estimated_cost_usd !== null
          ? formatUsd(job.estimated_cost_usd)
          : "--"}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">
        {job.seed !== null ? job.seed : "--"}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">
        {job.created_at ? new Date(job.created_at).toLocaleTimeString() : "--"}
      </td>
      <td className="px-3 py-2">
        {(job.error_message || actionError) && (
          <span
            className="inline-block max-w-[200px] truncate text-xs text-red-400"
            title={actionError ?? job.error_message ?? ""}
          >
            {actionError ?? job.error_message}
          </span>
        )}
      </td>
      <td className="px-3 py-2">
        <div className="flex gap-1">
          {(job.status === "Queued" || job.status === "Running") && (
            <button
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
              className="rounded p-1.5 text-zinc-500 hover:bg-red-900/50 hover:text-red-400"
              title="Cancel"
            >
              <Ban size={14} />
            </button>
          )}
          {(job.status === "Failed" || job.status === "Cancelled") && (
            <button
              onClick={() => retryMut.mutate()}
              disabled={retryMut.isPending}
              className="rounded p-1.5 text-zinc-500 hover:bg-blue-900/50 hover:text-blue-400"
              title="Retry"
            >
              <RefreshCw size={14} />
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
  const { currentProjectId } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const runTab: RunTab =
    requestedTab === "failed" ||
    requestedTab === "completed" ||
    requestedTab === "history"
      ? requestedTab
      : "current";
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [simulationAckProjectId, setSimulationAckProjectId] = useState<
    string | null
  >(null);
  // Analysing a workflow is a real backend cost, so the diagnostics queries
  // only mount once the disclosure has actually been opened.
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [historyLimit, setHistoryLimit] = useState(50);
  const [imageWorkflowId, setImageWorkflowId] = useState("");
  const [videoWorkflowId, setVideoWorkflowId] = useState("");

  // ── Queries ────────────────────────────────────────────────────────────
  const workflowsQ = useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows.list,
  });

  const providersQ = useQuery({
    queryKey: ["media-providers"],
    queryFn: api.media.providers,
    staleTime: 5 * 60 * 1000,
  });

  const mediaHealthQ = useQuery({
    queryKey: ["media-health"],
    queryFn: api.media.health,
    refetchInterval: 30_000,
  });

  const projectQ = useQuery({
    queryKey: ["selected-project", currentProjectId],
    queryFn: () => api.projects.get(currentProjectId!),
    enabled: !!currentProjectId,
  });
  const projectAvailable = projectQ.isSuccess;

  const jobsQ = useQuery({
    queryKey: ["jobs", currentProjectId],
    queryFn: () => api.generation.listJobs(currentProjectId!),
    enabled: !!currentProjectId && projectAvailable,
    // Keep checking even after an empty first response so jobs created by a
    // worker or another browser session become visible here.
    refetchInterval: projectAvailable ? 2000 : false,
  });
  const hasJobs = (jobsQ.data?.length ?? 0) > 0;

  const preflightQ = useQuery({
    queryKey: ["preflight", currentProjectId],
    queryFn: () => api.generation.preflight(currentProjectId!),
    enabled: !!currentProjectId && projectAvailable,
    refetchInterval: hasJobs ? 2000 : false,
  });

  // Safe to fetch on load: the estimate endpoint creates nothing and calls no
  // vendor API, so the cost is on screen before Generate is ever pressed.
  const estimateQ = useQuery({
    queryKey: ["generation-estimate", currentProjectId],
    queryFn: () => api.generation.estimate(currentProjectId!),
    enabled: !!currentProjectId && projectAvailable,
    refetchInterval: hasJobs ? 2000 : false,
  });

  const queueStatusQ = useQuery({
    queryKey: ["queue-status", currentProjectId],
    queryFn: () => api.generation.queueStatus(currentProjectId!),
    enabled: !!currentProjectId && projectAvailable,
    refetchInterval: hasJobs ? 2000 : false,
  });

  const currentRunQ = useQuery({
    queryKey: ["generation-run-current", currentProjectId],
    queryFn: () => api.generation.currentRun(currentProjectId!),
    enabled: !!currentProjectId && projectAvailable && runTab !== "history",
    refetchInterval: projectAvailable ? 2000 : false,
  });

  const runsQ = useQuery({
    queryKey: ["generation-runs", currentProjectId, historyLimit + 1],
    queryFn: () => api.generation.listRuns(currentProjectId!, historyLimit + 1),
    enabled: !!currentProjectId && projectAvailable && runTab === "history",
    refetchInterval: runTab === "history" ? 2000 : false,
  });

  // ── Mutations ──────────────────────────────────────────────────────────
  const generateMut = useMutation({
    mutationFn: (confirmPaid: boolean) =>
      api.generation.start(currentProjectId!, undefined, confirmPaid),
    onSuccess: () => {
      setConfirmOpen(false);
      qc.invalidateQueries({ queryKey: ["jobs", currentProjectId] });
      qc.invalidateQueries({ queryKey: ["preflight", currentProjectId] });
      qc.invalidateQueries({ queryKey: ["generation-estimate", currentProjectId] });
      qc.invalidateQueries({ queryKey: ["generation-run-current", currentProjectId] });
      qc.invalidateQueries({ queryKey: ["generation-runs", currentProjectId] });
    },
  });

  const pauseMut = useMutation({
    mutationFn: () => api.generation.pauseQueue(currentProjectId!),
    onSuccess: (status) =>
      qc.setQueryData(["queue-status", currentProjectId], status),
  });

  const resumeMut = useMutation({
    mutationFn: () => api.generation.resumeQueue(currentProjectId!),
    onSuccess: (status) =>
      qc.setQueryData(["queue-status", currentProjectId], status),
  });

  const applyWorkflowsMut = useMutation({
    mutationFn: ({ imageId, videoId }: { imageId: string; videoId: string }) =>
      api.projects.update(currentProjectId!, {
        default_image_workflow_id: imageId,
        default_video_workflow_id: videoId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["selected-project", currentProjectId],
      });
      qc.invalidateQueries({ queryKey: ["preflight", currentProjectId] });
      qc.invalidateQueries({
        queryKey: ["generation-estimate", currentProjectId],
      });
    },
  });

  const providerLabel = (id: MediaProviderId) =>
    providersQ.data?.providers.find((p) => p.id === id)?.label ?? id;

  // ── No project ─────────────────────────────────────────────────────────
  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <Zap size={32} className="mb-3 text-zinc-600" />
        <h2 className="text-lg font-semibold text-zinc-300">
          No Project Selected
        </h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  if (projectQ.isError) {
    const staleProjectId = currentProjectId;
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <AlertTriangle size={32} className="mb-3 text-amber-500" />
        <h2 className="text-lg font-semibold text-zinc-200">
          Project unavailable
        </h2>
        <p className="mt-1 max-w-md text-sm text-zinc-500">
          The selected project no longer exists or cannot be loaded. Cached
          generation jobs are hidden and no project actions will run.
        </p>
        <button
          onClick={() => {
            qc.removeQueries({
              predicate: (query) => query.queryKey.includes(staleProjectId),
            });
            qc.removeQueries({ queryKey: ["projects"] });
            dispatch({ type: "SET_PROJECT", id: null });
            navigate("/story");
          }}
          className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Switch project
        </button>
      </div>
    );
  }

  if (!projectAvailable) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-500">
        <Loader2 size={16} className="animate-spin" /> Checking selected project...
      </div>
    );
  }

  const estimate = estimateQ.data;
  const jobs = jobsQ.data;
  const queuePaused = queueStatusQ.data?.paused ?? false;
  const showQueueControl =
    (queueStatusQ.data?.queued ?? 0) + (queueStatusQ.data?.running ?? 0) > 0;
  const comfyuiHealth = mediaHealthQ.data?.providers.find(
    (provider) => provider.id === "comfyui",
  );
  const hasComfyuiShots =
    estimate?.shots.some((shot) => shot.provider_id === "comfyui") ?? false;
  const simulationRequired =
    comfyuiHealth?.mock === true && hasComfyuiShots;
  const comfyuiRuntimeUnavailable =
    hasComfyuiShots && comfyuiHealth?.online !== true;
  const simulationAcknowledged =
    simulationRequired && simulationAckProjectId === currentProjectId;
  const unrunnableWorkflows =
    workflowsQ.data?.filter((w) => w.source_format !== "api") ?? [];
  const validApiWorkflows =
    workflowsQ.data?.filter(
      (workflow) =>
        workflow.source_format === "api" &&
        workflow.validation_status === "valid",
    ) ?? [];
  const allImageWorkflows = validApiWorkflows.filter(
    (workflow) => workflow.purpose === "image",
  );
  const generalImageWorkflows = allImageWorkflows.filter(
    (workflow) => !("referenceImage" in workflow.parameter_mapping),
  );
  const imageWorkflows =
    generalImageWorkflows.length > 0 ? generalImageWorkflows : allImageWorkflows;
  const videoWorkflows = validApiWorkflows.filter(
    (workflow) =>
      workflow.purpose === "text-to-video" ||
      workflow.purpose === "image-to-video",
  );
  const selectedImageWorkflowId = imageWorkflows.some(
    (workflow) => workflow.id === imageWorkflowId,
  )
    ? imageWorkflowId
    : imageWorkflows.some(
          (workflow) =>
            workflow.id === projectQ.data?.default_image_workflow_id,
        )
      ? projectQ.data!.default_image_workflow_id!
      : (imageWorkflows[0]?.id ?? "");
  const selectedVideoWorkflowId = videoWorkflows.some(
    (workflow) => workflow.id === videoWorkflowId,
  )
    ? videoWorkflowId
    : videoWorkflows.some(
          (workflow) =>
            workflow.id === projectQ.data?.default_video_workflow_id,
        )
      ? projectQ.data!.default_video_workflow_id!
      : (videoWorkflows[0]?.id ?? "");
  const missingWorkflowBlocker =
    preflightQ.data?.issues.some((issue) =>
      issue.issues.includes(MISSING_WORKFLOW_BLOCKER),
    ) ?? false;

  const queuedCount = queueStatusQ.data?.queued ?? 0;
  const runningCount = queueStatusQ.data?.running ?? 0;
  const completedCount = queueStatusQ.data?.completed ?? 0;
  const failedCount = queueStatusQ.data?.failed ?? 0;
  const cancelledCount = queueStatusQ.data?.cancelled ?? 0;

  const onGenerate = () => {
    if (
      !estimate ||
      preflightQ.data?.ready !== true ||
      comfyuiRuntimeUnavailable ||
      (simulationRequired && !simulationAcknowledged)
    )
      return;
    generateMut.reset();
    if (estimate.requires_confirmation) {
      // A metered provider is involved: the amount has to be acknowledged
      // before the request is allowed to carry confirm_paid_generation.
      setConfirmOpen(true);
      return;
    }
    generateMut.mutate(false);
  };

  const generateError = generateMut.isError
    ? toAIError(generateMut.error).detail
    : null;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Zap size={20} className="text-indigo-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Generate</h1>
      </div>

      <RuntimeBanner
        health={mediaHealthQ.data}
        loading={mediaHealthQ.isLoading}
      />

      <ReadinessSummary
        preflight={preflightQ.data}
        loading={preflightQ.isFetching}
        error={preflightQ.isError ? toAIError(preflightQ.error).detail : null}
        onRerun={() => preflightQ.refetch()}
        catalogue={providersQ.data}
        mediaHealth={mediaHealthQ.data}
        unrunnableWorkflows={unrunnableWorkflows}
      />

      {missingWorkflowBlocker && (
        <WorkflowRecovery
          imageWorkflows={imageWorkflows}
          videoWorkflows={videoWorkflows}
          imageWorkflowId={selectedImageWorkflowId}
          videoWorkflowId={selectedVideoWorkflowId}
          onImageWorkflowChange={setImageWorkflowId}
          onVideoWorkflowChange={setVideoWorkflowId}
          onApply={() =>
            applyWorkflowsMut.mutate({
              imageId: selectedImageWorkflowId,
              videoId: selectedVideoWorkflowId,
            })
          }
          applying={applyWorkflowsMut.isPending}
          error={
            applyWorkflowsMut.isError
              ? toAIError(applyWorkflowsMut.error).detail
              : null
          }
        />
      )}

      <RunPanel
        estimate={estimate}
        loading={estimateQ.isLoading}
        error={estimateQ.isError ? toAIError(estimateQ.error).detail : null}
        providerLabel={providerLabel}
        onGenerate={onGenerate}
        generating={generateMut.isPending && !confirmOpen}
        generateError={confirmOpen ? null : generateError}
        queuePaused={queuePaused}
        showQueueControl={showQueueControl}
        onPause={() => pauseMut.mutate()}
        onResume={() => resumeMut.mutate()}
        queueBusy={pauseMut.isPending || resumeMut.isPending}
        simulationRequired={simulationRequired}
        simulationAcknowledged={simulationAcknowledged}
        onSimulationAcknowledged={(checked) =>
          setSimulationAckProjectId(checked ? currentProjectId : null)
        }
        comfyuiRuntimeUnavailable={comfyuiRuntimeUnavailable}
        preflightReady={preflightQ.data?.ready === true}
      />

      {/* Stats bar */}
      {queueStatusQ.data && queueStatusQ.data.total_jobs > 0 && (
        <div className="flex gap-4 text-xs">
          <span className="text-zinc-500">
            Total:{" "}
            <span className="text-zinc-300">{queueStatusQ.data.total_jobs}</span>
          </span>
          <span className="text-blue-400">Queued: {queuedCount}</span>
          <span className="text-yellow-400">Running: {runningCount}</span>
          <span className="text-green-400">Completed: {completedCount}</span>
          <span className="text-red-400">Failed: {failedCount}</span>
          <span className="text-zinc-400">Cancelled: {cancelledCount}</span>
          {queuePaused && (
            <span className="font-medium text-amber-300">Paused</span>
          )}
        </div>
      )}

      {/* Run-oriented queue: one Generate action remains one visible batch. */}
      <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
        <nav className="flex border-b border-zinc-800 px-2" aria-label="Generation queue views">
          {([
            ["current", "Current"],
            ["failed", "Failed"],
            ["completed", "Completed"],
            ["history", "History"],
          ] as [RunTab, string][]).map(([key, label]) => (
            <Link
              key={key}
              to={key === "current" ? "/generate" : `/generate?tab=${key}`}
              aria-current={runTab === key ? "page" : undefined}
              className={`border-b-2 px-4 py-3 text-sm font-medium ${
                runTab === key
                  ? "border-indigo-500 text-indigo-300"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="p-4">
          {runTab === "history" ? (
            runsQ.isError ? (
              <div className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                {toAIError(runsQ.error).detail}
              </div>
            ) : runsQ.data && runsQ.data.length > 0 ? (
              <div className="space-y-8">
                {runsQ.data.slice(0, historyLimit).map((run) => (
                  <RunSection key={run.id} run={run} />
                ))}
                {runsQ.data.length > historyLimit && (
                  <div className="text-center">
                    <button
                      type="button"
                      onClick={() => setHistoryLimit((value) => value + 50)}
                      className="rounded-md border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800"
                    >
                      Load 50 more runs
                    </button>
                  </div>
                )}
              </div>
            ) : runsQ.data ? (
              <p className="py-8 text-center text-sm text-zinc-500">No generation jobs yet.</p>
            ) : (
              <p className="py-8 text-center text-sm text-zinc-500">Loading run history...</p>
            )
          ) : currentRunQ.data ? (
            <RunSection
              run={currentRunQ.data}
              jobs={currentRunQ.data.jobs.filter((job) =>
                runTab === "failed"
                  ? job.status === "Failed"
                  : runTab === "completed"
                    ? job.status === "Completed"
                    : true,
              )}
            />
          ) : currentRunQ.data === null ? (
            <p className="py-8 text-center text-sm text-zinc-500">No generation jobs yet.</p>
          ) : (
            <p className="py-8 text-center text-sm text-zinc-500">Loading current run...</p>
          )}
        </div>
      </div>

      {/* Legacy job detail table retains provider evidence and job actions. */}
      {runTab === "current" && (
        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
        <div className="border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-200">Job Queue</h2>
        </div>

        {jobsQ.isLoading && (
          <div className="flex items-center justify-center gap-2 px-4 py-8 text-sm text-zinc-500">
            <Loader2 size={14} className="animate-spin" /> Loading jobs...
          </div>
        )}

        {jobsQ.isError && (
          <div className="flex items-start gap-2 px-4 py-6 text-sm text-red-300">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            {toAIError(jobsQ.error).detail}
          </div>
        )}

        {jobs && jobs.length === 0 && (
          <div className="flex flex-col items-center py-12 text-center">
            <Clock size={24} className="mb-2 text-zinc-600" />
            <p className="text-sm text-zinc-500">
              No generation jobs yet. Clear preflight and press Generate to
              start.
            </p>
          </div>
        )}

        {jobs && jobs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-zinc-800 text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="px-3 py-2">Shot</th>
                  <th className="px-3 py-2">Provider</th>
                  <th className="px-3 py-2">Model</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Attempts</th>
                  <th className="px-3 py-2">Est. cost</th>
                  <th className="px-3 py-2">Seed</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Error</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    projectId={currentProjectId}
                    providerLabel={providerLabel}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        </div>
      )}

      {/* Advanced diagnostics: everything needed to fix a workflow, and
          nothing needed to decide whether to generate. */}
      <details
        className="rounded-lg border border-zinc-800 bg-zinc-900/40"
        onToggle={(e) => setDiagnosticsOpen(e.currentTarget.open)}
      >
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-300">
          <Wrench size={14} className="text-zinc-500" />
          Advanced diagnostics
          <span className="text-xs font-normal text-zinc-500">
            workflow formats, node mappings, per-shot preflight detail
          </span>
        </summary>

        {diagnosticsOpen && (
          <div className="space-y-4 border-t border-zinc-800 px-4 py-4">
            {/* Registered workflows ComfyUI cannot execute */}
            {unrunnableWorkflows.map((w) => (
              <WorkflowFormatPanel key={w.id} workflow={w} />
            ))}

            {/* Mapping validation per workflow */}
            {preflightQ.data && preflightQ.data.workflow_checks.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                  Workflow mapping
                </h3>
                {preflightQ.data.workflow_checks.map((check) => (
                  <div
                    key={check.workflow_id}
                    className="flex items-start gap-2 rounded-md bg-zinc-800/50 px-3 py-1.5 text-xs"
                  >
                    {check.valid ? (
                      <CheckCircle2
                        size={12}
                        className="mt-0.5 shrink-0 text-green-500"
                      />
                    ) : (
                      <XCircle
                        size={12}
                        className="mt-0.5 shrink-0 text-red-500"
                      />
                    )}
                    <div className="min-w-0">
                      <span className="font-medium text-zinc-300">
                        {check.name || check.workflow_id.slice(0, 8)}
                      </span>
                      <span className="ml-1.5 text-zinc-500">
                        {check.source_format}-format
                      </span>
                      {check.errors.map((err) => (
                        <p key={err} className="mt-0.5 text-red-400">
                          {err}
                        </p>
                      ))}
                      {check.warnings.map((warn) => (
                        <p key={warn} className="mt-0.5 text-amber-400">
                          {warn}
                        </p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Per-shot preflight detail behind the grouped summary above */}
            {preflightQ.data && preflightQ.data.issues.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                  Blocked shots
                </h3>
                {preflightQ.data.issues.map((issue) => (
                  <div
                    key={issue.shot_id}
                    className="flex items-start gap-2 rounded-md px-3 py-1.5 text-xs"
                  >
                    <XCircle size={12} className="mt-0.5 shrink-0 text-red-500" />
                    <div className="min-w-0">
                      <span className="font-medium text-zinc-300">
                        Shot {issue.shot_order}
                      </span>
                      <span className="ml-1 font-mono text-zinc-500">
                        {issue.shot_id.slice(0, 8)}
                      </span>
                      {issue.issues.map((text) => (
                        <p key={text} className="mt-0.5 text-zinc-400">
                          {text}
                        </p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Per-shot plan: exactly what each shot would submit */}
            {estimate && estimate.shots.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                  Planned per shot
                </h3>
                {estimate.shots.map((plan) => (
                  <div
                    key={plan.shot_id}
                    className="flex flex-wrap items-center gap-2 rounded-md bg-zinc-800/50 px-3 py-1.5 text-xs"
                  >
                    <span className="font-mono text-zinc-400">
                      {plan.shot_id.slice(0, 8)}
                    </span>
                    <span className="text-zinc-300">
                      {providerLabel(plan.provider_id)}
                    </span>
                    <span className="font-mono text-zinc-500">{plan.model}</span>
                    <span className="text-zinc-500">{plan.generation_mode}</span>
                    <span className="ml-auto text-zinc-300">
                      {plan.paid
                        ? plan.estimated_cost_usd !== null
                          ? formatUsd(plan.estimated_cost_usd)
                          : "no published rate"
                        : "local"}
                    </span>
                    {plan.blockers.map((b) => (
                      <p key={b} className="w-full text-red-400">
                        {b}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {unrunnableWorkflows.length === 0 &&
              !preflightQ.data?.issues.length && (
                <p className="text-xs text-zinc-500">
                  Nothing to report: every registered workflow is API-format and
                  no shot is blocked.
                </p>
              )}
          </div>
        )}
      </details>

      {/* Paid-run gate. Only reachable when the estimate says a metered
          provider is involved. */}
      <CostConfirmDialog
        open={confirmOpen}
        title="This run uses a metered provider"
        lines={
          estimate
            ? [
                { label: "Shots in this run", value: String(estimate.shot_count) },
                { label: "Paid shots", value: String(estimate.paid_shot_count) },
                ...estimate.providers.map((p) => ({
                  label: `${providerLabel(p.provider_id)} (${p.model})`,
                  value: p.paid
                    ? p.estimated_cost_usd !== null
                      ? `${p.shot_count} shot(s), ${formatUsd(p.estimated_cost_usd)}`
                      : `${p.shot_count} shot(s), no published rate`
                    : `${p.shot_count} shot(s), no API charge`,
                })),
              ]
            : []
        }
        amountText={
          estimate?.estimated_cost_usd !== null &&
          estimate?.estimated_cost_usd !== undefined
            ? formatUsd(estimate.estimated_cost_usd)
            : "No published rate for the selected model"
        }
        costBasis={
          estimate?.providers.find((p) => p.paid && p.cost_basis)?.cost_basis
        }
        notes={[
          ...(estimate && estimate.unpriced_paid_shots > 0
            ? [
                `${estimate.unpriced_paid_shots} paid shot(s) have no published rate, so the real charge may exceed the amount above.`,
              ]
            : []),
          ...(estimate?.blockers ?? []),
        ]}
        confirmLabel="Generate now"
        acknowledgement={
          estimate?.estimated_cost_usd !== null &&
          estimate?.estimated_cost_usd !== undefined
            ? `I understand this starts ${estimate.paid_shot_count} paid generation(s) costing about ${formatUsd(estimate.estimated_cost_usd)}, billed to the account configured on this machine.`
            : "I understand this starts paid generations billed to the account configured on this machine, at a rate this build cannot quote."
        }
        busy={generateMut.isPending}
        error={generateError}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => generateMut.mutate(true)}
      />
    </div>
  );
}
