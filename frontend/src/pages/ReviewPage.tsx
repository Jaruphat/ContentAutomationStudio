/* ──────────────────────────────────────────────────────────────────────────
   ReviewPage -- the takes, at a size a reviewer can actually judge.

   Every card reserves the same 16:9 media area and shows what produced the
   take, because "approve" is a decision about an image and its provenance, not
   about a row of identifiers. Regenerating on a metered provider goes through
   an explicit priced confirmation: a reject-and-retry loop is the easiest way
   to spend money by accident.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
import api, { toAIError } from "../api/client";
import { useAppState, useAppDispatch } from "../store/useProjectStore";
import StatusBadge from "../components/StatusBadge";
import TakePreview from "../components/TakePreview";
import CostConfirmDialog from "../components/CostConfirmDialog";
import type { MediaProviderId, Take } from "../types";

type FilterMode = "all" | "Pending" | "Approved" | "Rejected";

function formatUsd(amount: number): string {
  return amount.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

export function reviewRunPath(runId: string): string {
  return `/review?run=${encodeURIComponent(runId)}`;
}

// ── Take card ────────────────────────────────────────────────────────────

function TakeCard({
  take,
  projectId,
  providerLabel,
  isSelected,
  onSelect,
}: {
  take: Take;
  projectId: string;
  providerLabel: (id: MediaProviderId) => string;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [checkingEstimate, setCheckingEstimate] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["takes", projectId] });
    qc.invalidateQueries({ queryKey: ["jobs", projectId] });
  };

  const approveMut = useMutation({
    mutationFn: () => api.review.approve(take.id),
    onSuccess: invalidate,
  });

  const rejectMut = useMutation({
    mutationFn: () => api.review.reject(take.id),
    onSuccess: invalidate,
  });

  const regenMut = useMutation({
    mutationFn: (confirmPaid: boolean) =>
      api.review.regenerate(take.shot_id, confirmPaid),
    onSuccess: (job) => {
      setConfirmOpen(false);
      invalidate();
      if (job.run_id) navigate(reviewRunPath(job.run_id));
    },
  });

  /*
   * The price is re-read from the backend when the dialog opens rather than
   * taken from the take, so what is confirmed is what the *next* run costs
   * under today's configuration, not what the previous one happened to cost.
   */
  const estimateQ = useQuery({
    queryKey: ["regenerate-estimate", take.shot_id],
    queryFn: () => api.review.regenerationEstimate(take.shot_id),
    enabled: false,
  });

  const estimate = estimateQ.data;
  const shotPlan = estimate?.shots[0];

  // Approve/reject failures and unconfirmed regenerate failures are shown on
  // the card; a failure raised from inside the dialog is shown in the dialog.
  const cardError = approveMut.isError
    ? toAIError(approveMut.error).detail
    : rejectMut.isError
      ? toAIError(rejectMut.error).detail
      : estimateQ.isError && !confirmOpen
        ? toAIError(estimateQ.error).detail
        : regenMut.isError && !confirmOpen
          ? toAIError(regenMut.error).detail
          : null;

  const onRegenerateClick = async () => {
    regenMut.reset();
    setCheckingEstimate(true);
    const result = await estimateQ.refetch();
    setCheckingEstimate(false);
    if (!result.data || result.error) return;
    if (result.data.requires_confirmation) {
      setConfirmOpen(true);
      return;
    }
    // Local generation is not metered, so it needs no price confirmation. The
    // backend still refuses with 409 if that provider is unusable here, and
    // that message is surfaced on the card.
    regenMut.mutate(false);
  };

  const amountText = estimateQ.isLoading
    ? "Checking the current price..."
    : estimate && estimate.estimated_cost_usd !== null
      ? formatUsd(estimate.estimated_cost_usd)
      : "No published rate for this model";

  const dialogNotes = [
    ...(estimate?.blockers ?? []),
    ...(estimate && estimate.unpriced_paid_shots > 0
      ? [
          "This provider publishes no rate for this model, so the charge " +
            "cannot be shown before the run.",
        ]
      : []),
  ];

  return (
    <div
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={`Select take ${take.id}`}
      className={`cursor-pointer overflow-hidden rounded-lg border bg-zinc-900/70 transition-colors ${
        isSelected
          ? "border-indigo-500 ring-1 ring-indigo-500/30"
          : "border-zinc-800 hover:border-zinc-700"
      }`}
    >
      <TakePreview take={take} className="rounded-none border-0 border-b" />

      <div className="space-y-2 p-3">
        {/* Identity and review state */}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate font-mono text-[11px] text-zinc-500">
            Shot {take.shot_id.slice(0, 8)}
          </span>
          <StatusBadge status={take.review_status} />
        </div>

        {/* What produced it, and what that cost */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-300">
            {providerLabel(take.media_provider_id)}
          </span>
          {take.media_model && (
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
              {take.media_model}
            </span>
          )}
          {take.estimated_cost_usd !== null && take.estimated_cost_usd > 0 && (
            <span className="rounded bg-amber-900 px-1.5 py-0.5 text-[11px] font-medium text-amber-300">
              {formatUsd(take.estimated_cost_usd)}
            </span>
          )}
        </div>

        <div className="space-y-0.5 text-xs text-zinc-400">
          {take.width > 0 && (
            <div>
              {take.width}x{take.height}
              {take.duration_sec > 0 ? ` - ${take.duration_sec}s` : ""}
            </div>
          )}
          {take.width === 0 && take.duration_sec > 0 && (
            <div>{take.duration_sec}s</div>
          )}
          {take.notes && (
            <div className="truncate italic text-zinc-500">{take.notes}</div>
          )}
        </div>

        {cardError && (
          <div className="flex items-start gap-1.5 rounded-md border border-red-800 bg-red-900/30 px-2 py-1.5 text-[11px] text-red-300">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span>{cardError}</span>
          </div>
        )}

        {/* Actions sit below the media, so nothing ever covers the imagery. */}
        <div className="flex gap-1.5 border-t border-zinc-800 pt-2">
          {take.review_status === "Pending" && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  approveMut.mutate();
                }}
                disabled={approveMut.isPending}
                className="flex h-8 flex-1 items-center justify-center gap-1 rounded-md bg-green-800/60 px-2 text-xs font-medium text-green-300 hover:bg-green-700/60 disabled:opacity-50"
              >
                {approveMut.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <ThumbsUp size={12} />
                )}
                Approve
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  rejectMut.mutate();
                }}
                disabled={rejectMut.isPending}
                className="flex h-8 flex-1 items-center justify-center gap-1 rounded-md bg-red-900/50 px-2 text-xs font-medium text-red-300 hover:bg-red-800/50 disabled:opacity-50"
              >
                {rejectMut.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <ThumbsDown size={12} />
                )}
                Reject
              </button>
            </>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRegenerateClick();
            }}
            disabled={regenMut.isPending || confirmOpen || checkingEstimate}
            className="flex h-8 items-center justify-center gap-1 rounded-md border border-zinc-700 px-2.5 text-xs font-medium text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
            title={
              estimate?.requires_confirmation
                ? "Regenerate on a metered provider -- asks for confirmation"
                : "Regenerate"
            }
          >
            {regenMut.isPending || checkingEstimate ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <RefreshCw size={12} />
            )}
            Regenerate
          </button>
        </div>
      </div>

      {/* The dialog is a fixed overlay drawn over the whole page; clicks inside
          it must not fall through to the card that opened it. */}
      <div onClick={(e) => e.stopPropagation()}>
        <CostConfirmDialog
          open={confirmOpen}
          title="Regenerate this shot on a metered provider"
          lines={[
            { label: "Shot", value: take.shot_id.slice(0, 8) },
            {
              label: "Provider",
              value: providerLabel(
                shotPlan?.provider_id ?? take.media_provider_id,
              ),
            },
            {
              label: "Model",
              value: shotPlan?.model || take.media_model || "--",
            },
            { label: "Images", value: "1" },
          ]}
          amountText={amountText}
          costBasis={shotPlan?.cost_basis}
          notes={dialogNotes}
          confirmLabel="Regenerate"
          acknowledgement={`I understand this starts one paid generation on ${providerLabel(
            shotPlan?.provider_id ?? take.media_provider_id,
          )}, billed to the account configured on this machine.`}
          busy={regenMut.isPending || estimateQ.isFetching}
          confirmDisabled={estimateQ.isError}
          error={
            regenMut.isError
              ? toAIError(regenMut.error).detail
              : estimateQ.isError
                ? toAIError(estimateQ.error).detail
                : null
          }
          onCancel={() => setConfirmOpen(false)}
          onConfirm={() => regenMut.mutate(true)}
        />
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
  const [searchParams] = useSearchParams();
  const runId = searchParams.get("run");

  const takesQ = useQuery({
    queryKey: ["takes", currentProjectId, runId],
    queryFn: () => api.review.listTakes(currentProjectId!, runId),
    enabled: !!currentProjectId,
    refetchInterval: 3000,
  });

  const runQ = useQuery({
    queryKey: ["generation-run", runId],
    queryFn: () => api.generation.getRun(runId!),
    enabled: !!runId,
  });

  // Only used to turn a provider id into the label the catalogue publishes.
  const providersQ = useQuery({
    queryKey: ["media-providers"],
    queryFn: api.media.providers,
    staleTime: 5 * 60 * 1000,
  });

  const providerLabel = (id: MediaProviderId) =>
    providersQ.data?.providers.find((p) => p.id === id)?.label ?? id;

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <CheckCircle size={32} className="mb-3 text-zinc-500" />
        <h2 className="text-lg font-semibold text-zinc-300">
          No Project Selected
        </h2>
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
    <div className="mx-auto max-w-7xl space-y-6 px-6 py-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CheckCircle size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Review Takes</h1>
          {takesQ.data && (
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400">
              {takesQ.data.length} take{takesQ.data.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {runId && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-indigo-800/60 bg-indigo-950/30 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-indigo-200">
              Reviewing {runQ.data?.label ?? runId}
            </p>
            <p className="mt-0.5 text-xs text-indigo-300/70">
              Only takes produced by this generation run are shown.
            </p>
          </div>
          <Link
            to="/review"
            className="rounded-md border border-indigo-700 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-900/50"
          >
            Show all takes
          </Link>
        </div>
      )}

      {/* Hand-off to Timeline: once anything is approved, that is the next
          stage, and "everything reviewed" should not read like a dead end. */}
      {(() => {
        const approvedCount =
          takesQ.data?.filter((t) => t.review_status === "Approved").length ?? 0;
        const pendingCount =
          takesQ.data?.filter((t) => t.review_status === "Pending").length ?? 0;
        if (approvedCount === 0) return null;
        const done = pendingCount === 0;
        // Under a run filter, "done" only means this run has nothing left
        // pending - the rest of the project may still have takes to review,
        // so the message must not claim more than this scoped list showed.
        const doneMessage = runId
          ? "This run is fully reviewed. Build the timeline to assemble your approved takes."
          : "Every take has been reviewed. Build the timeline to assemble your approved takes.";
        return (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-4 py-3">
            <p className="text-sm text-emerald-200">
              {done
                ? doneMessage
                : `${approvedCount} approved, ${pendingCount} still ${pendingCount === 1 ? "needs" : "need"} review.`}
            </p>
            <Link
              to="/timeline"
              className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
            >
              {done ? "Build the timeline" : "Go to Timeline"}
            </Link>
          </div>
        );
      })()}

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
            aria-pressed={filter === key}
            className={`h-8 rounded-full px-3.5 text-xs font-medium transition-colors ${
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
        <div className="flex items-center justify-center gap-2 py-12 text-zinc-500">
          <Loader2 size={14} className="animate-spin" /> Loading takes...
        </div>
      )}

      {/* Error */}
      {takesQ.isError && (
        <div className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          {toAIError(takesQ.error).detail}
        </div>
      )}

      {/* Empty */}
      {filtered && filtered.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Image size={28} className="mb-2 text-zinc-500" />
          <p className="text-sm text-zinc-500">
            {filter === "all"
              ? runId
                ? `No takes are available for ${runQ.data?.label ?? runId}.`
                : "No takes generated yet. Go to Generate to create them."
              : `No ${filter.toLowerCase()} takes found.`}
          </p>
        </div>
      )}

      {/* Grid: three to four judgeable cards per desktop row. */}
      {filtered && filtered.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {filtered.map((take) => (
            <TakeCard
              key={take.id}
              take={take}
              projectId={currentProjectId}
              providerLabel={providerLabel}
              isSelected={selectedTakeId === take.id}
              onSelect={() => dispatch({ type: "SELECT_TAKE", id: take.id })}
            />
          ))}
        </div>
      )}
    </div>
  );
}
