/* ──────────────────────────────────────────────────────────────────────────
   ActionError -- what actually went wrong, in the place the action was taken.

   A button that reports "Failed." tells the user nothing they can act on: a
   refused stale timeline, an unreachable backend and a missing project all
   look identical. Every failure shown through this component carries the
   backend's own message, so the next step is readable from the screen.
   ────────────────────────────────────────────────────────────────────────── */

import { AlertCircle } from "lucide-react";
import { toAIError } from "../api/client";

export default function ActionError({
  label,
  error,
}: {
  label: string;
  error: unknown;
}) {
  if (!error) return null;

  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/30 px-3 py-2 text-sm text-red-300"
    >
      <AlertCircle size={14} className="mt-0.5 shrink-0" />
      <span>
        <span className="font-medium">{label} failed.</span>{" "}
        {toAIError(error).detail}
      </span>
    </div>
  );
}
