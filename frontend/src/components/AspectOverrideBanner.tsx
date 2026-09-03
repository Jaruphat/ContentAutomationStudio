import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { DeliveryValidation, DeliveryWarning } from "../types";

export default function AspectOverrideBanner({
  warnings,
  validation,
}: {
  warnings?: DeliveryWarning[];
  validation?: DeliveryValidation;
}) {
  const overrides = (warnings ?? []).filter(
    (warning) => warning.code === "e2e_aspect_override",
  );
  if (overrides.length === 0) return null;

  // An override warning without validation is an incomplete backend response.
  // Never turn missing status into a visual pass.
  const pipelinePass = validation?.pipeline_pass === true;
  const deliverySpecPass = validation?.delivery_spec_pass === true;

  const takeCount = new Set(overrides.flatMap((warning) => warning.take_ids)).size;
  return (
    <section
      aria-label="E2E aspect override warning"
      className="rounded-lg border-2 border-amber-500/70 bg-amber-950/40 p-4 text-amber-100"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={20} className="mt-0.5 shrink-0 text-amber-400" />
        <div className="space-y-2">
          {overrides.map((warning) => (
            <p key={warning.message} className="text-sm font-semibold">
              {warning.message}
            </p>
          ))}
          <p className="text-xs text-amber-200/80">
            Current timeline includes {takeCount} waived take
            {takeCount === 1 ? "" : "s"}. This is a scoped test exception, not
            a project-wide validation bypass.
          </p>
          <div className="flex flex-wrap gap-2 text-xs font-medium">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/50 px-2 py-1 text-emerald-300">
              <CheckCircle2 size={12} />
              {pipelinePass ? "Pipeline pass" : "Pipeline not passed"}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-red-950/60 px-2 py-1 text-red-300">
              <XCircle size={12} />
              {deliverySpecPass
                ? "Delivery spec pass"
                : "Delivery spec not passed"}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
