/* ──────────────────────────────────────────────────────────────────────────
   CostConfirmDialog -- the gate in front of a metered generation.

   Spending money is not an "OK / Cancel" decision: the amount, what produces
   it and how it was derived all have to be on screen, and the user has to tick
   an acknowledgement before the confirm button becomes usable. That is also
   why this is a dialog rather than window.confirm -- a native confirm cannot
   show a breakdown, and its default action is one keypress away.
   ────────────────────────────────────────────────────────────────────────── */

import { useEffect, useId, useState } from "react";
import { AlertCircle, AlertTriangle, Loader2 } from "lucide-react";

export interface CostConfirmLine {
  label: string;
  value: string;
}

export interface CostConfirmDialogProps {
  open: boolean;
  title: string;
  /** What the run consists of: provider, model, shot counts, per-provider cost. */
  lines: CostConfirmLine[];
  /** The amount being authorised, already formatted for display. */
  amountText: string;
  /** How the amount was derived, in the pricing source's own words. */
  costBasis?: string;
  /** Caveats: unpriced shots, providers that are not configured, blockers. */
  notes?: string[];
  confirmLabel: string;
  /** Sentence the user must tick. Should restate the amount. */
  acknowledgement: string;
  busy?: boolean;
  /** Set when the price could not be established; blocks confirmation. */
  confirmDisabled?: boolean;
  /** Already-sanitised message; never a raw exception. */
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function CostConfirmDialog({
  open,
  title,
  lines,
  amountText,
  costBasis,
  notes = [],
  confirmLabel,
  acknowledgement,
  busy = false,
  confirmDisabled = false,
  error = null,
  onCancel,
  onConfirm,
}: CostConfirmDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const checkboxId = useId();
  const titleId = useId();

  // Every opening is a fresh authorisation: a tick from last time must not
  // carry over to a different run with a different price.
  useEffect(() => {
    if (open) setAcknowledged(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-lg rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl"
      >
        <div className="flex items-center gap-2 border-b border-zinc-800 px-5 py-3">
          <AlertTriangle size={16} className="text-amber-400" />
          <h2 id={titleId} className="text-sm font-semibold text-zinc-100">
            {title}
          </h2>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="rounded-md border border-amber-800/60 bg-amber-900/25 px-4 py-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-amber-300">
              Estimated charge
            </p>
            <p className="mt-0.5 text-xl font-semibold text-amber-200">
              {amountText}
            </p>
            {costBasis && (
              <p className="mt-1 text-xs text-amber-100/80">{costBasis}</p>
            )}
          </div>

          {lines.length > 0 && (
            <dl className="divide-y divide-zinc-800 rounded-md border border-zinc-800">
              {lines.map((line) => (
                <div
                  key={`${line.label}-${line.value}`}
                  className="flex items-start justify-between gap-4 px-3 py-2"
                >
                  <dt className="text-xs text-zinc-400">{line.label}</dt>
                  <dd className="text-right text-xs font-medium text-zinc-200">
                    {line.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {notes.length > 0 && (
            <ul className="space-y-1">
              {notes.map((note) => (
                <li
                  key={note}
                  className="flex items-start gap-2 text-xs text-zinc-400"
                >
                  <AlertCircle size={12} className="mt-0.5 shrink-0 text-zinc-500" />
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          )}

          <label
            htmlFor={checkboxId}
            className="flex cursor-pointer items-start gap-2 rounded-md border border-zinc-800 bg-zinc-800/40 px-3 py-2.5"
          >
            <input
              id={checkboxId}
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              disabled={busy}
              className="mt-0.5 h-4 w-4 shrink-0 accent-indigo-500"
            />
            <span className="text-xs text-zinc-300">{acknowledgement}</span>
          </label>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-3 py-2 text-xs text-red-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-800 px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-zinc-700 px-4 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!acknowledged || busy || confirmDisabled}
            className="flex items-center gap-1.5 rounded-md bg-amber-600 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && <Loader2 size={13} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
