/* ──────────────────────────────────────────────────────────────────────────
   PublishGate -- the scorecard, and the package it stands in front of.

   Take review answers "is this shot usable". This answers the decision that
   is made once: does this episode go out. Nine measures with a target each,
   and one question that outranks all nine - would a viewer know this was AI
   within two seconds? A yes fails the gate whatever the numbers say, because
   nobody watching gets as far as the numbers.

   Not ready is the default and every blocker is named. A package that reports
   ready when it is not is worse than no package, because it is believed.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Send, XCircle } from "lucide-react";
import api, { toAIError } from "../api/client";
import ActionError from "./ActionError";

export default function PublishGate({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [aiTell, setAiTell] = useState(false);
  const [causes, setCauses] = useState("");
  const [notes, setNotes] = useState("");

  const rubricQ = useQuery({
    queryKey: ["quality-rubric"],
    queryFn: api.quality.rubric,
    staleTime: Infinity,
  });
  const reviewQ = useQuery({
    queryKey: ["quality-review", projectId],
    queryFn: () => api.quality.latest(projectId),
  });
  const packageQ = useQuery({
    queryKey: ["publish-package", projectId],
    queryFn: () => api.publishing.get(projectId),
  });

  const record = useMutation({
    mutationFn: () =>
      api.quality.record(projectId, {
        scores,
        ai_tell: aiTell,
        ai_tell_causes: causes,
        notes,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quality-review", projectId] });
      qc.invalidateQueries({ queryKey: ["publish-package", projectId] });
    },
  });

  const rubric = rubricQ.data ?? [];
  const latest = reviewQ.data;
  const pkg = packageQ.data;

  return (
    <section className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center gap-2">
        <Send size={14} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-zinc-200">Publish gate</h2>
        {latest?.reviewed && (
          <span
            className={`rounded px-2 py-0.5 text-[10px] ${
              latest.passed
                ? "bg-emerald-950 text-emerald-300"
                : "bg-red-950 text-red-300"
            }`}
          >
            {latest.passed ? "Passed" : "Not passed"}
          </span>
        )}
      </div>

      {/* -- The scorecard --------------------------------------------------
          Every metric carries the question it is really asking. A number with
          no question behind it gets scored 8 every time. */}
      <div className="space-y-2">
        {rubric.map((metric) => (
          <label key={metric.key} className="block text-xs text-zinc-400">
            <span className="flex flex-wrap items-baseline gap-2">
              <span className="font-medium text-zinc-300">{metric.label}</span>
              <span className="text-[10px] text-zinc-500">
                needs {metric.target}
              </span>
            </span>
            <span className="mt-0.5 block text-[10px] leading-snug text-zinc-500">
              {metric.question}
            </span>
            <input
              type="number"
              min={1}
              max={10}
              value={scores[metric.key] ?? ""}
              onChange={(e) =>
                setScores((current) => ({
                  ...current,
                  [metric.key]: e.target.value === "" ? null : Number(e.target.value),
                }))
              }
              className="mt-1 w-20 rounded px-2 py-1 text-sm"
            />
          </label>
        ))}
      </div>

      <label className="flex items-start gap-2 text-xs text-amber-300">
        <input
          type="checkbox"
          checked={aiTell}
          onChange={(e) => setAiTell(e.target.checked)}
        />
        Would a viewer know this was AI within two seconds? A yes fails the gate
        whatever the scores say.
      </label>
      {aiTell && (
        <label className="block text-xs text-zinc-400">
          What gives it away, and in which shots
          <textarea
            rows={2}
            value={causes}
            onChange={(e) => setCauses(e.target.value)}
            placeholder="plastic faces in shots 6 and 7"
            className="mt-1 w-full rounded px-2 py-1 text-sm"
          />
          <span className="mt-0.5 block text-[10px] text-zinc-500">
            Required. "It looks like AI" regenerates nothing; naming the shots
            regenerates those shots.
          </span>
        </label>
      )}

      <label className="block text-xs text-zinc-400">
        Notes
        <textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mt-1 w-full rounded px-2 py-1 text-sm"
        />
      </label>

      <button
        type="button"
        onClick={() => record.mutate()}
        disabled={record.isPending}
        className="flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
      >
        {record.isPending ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <CheckCircle2 size={12} />
        )}
        Record review
      </button>
      <ActionError label="Record quality review" error={record.error} />

      {latest?.reviewed && latest.reasons.length > 0 && (
        <ul className="space-y-1">
          {latest.reasons.map((reason) => (
            <li
              key={reason}
              className="rounded border border-amber-900/60 bg-amber-950/30 px-2 py-1 text-[11px] text-amber-200"
            >
              {reason}
            </li>
          ))}
        </ul>
      )}

      {/* -- The package ---------------------------------------------------- */}
      {pkg && (
        <div className="space-y-2 border-t border-zinc-800 pt-3">
          <div className="flex items-center gap-2">
            {pkg.ready ? (
              <CheckCircle2 size={14} className="text-emerald-400" />
            ) : (
              <XCircle size={14} className="text-red-400" />
            )}
            <span className="text-xs font-medium text-zinc-200">
              {pkg.ready ? "Ready to publish" : "Not ready to publish"}
            </span>
          </div>
          {pkg.blockers.map((blocker) => (
            <p key={blocker} className="text-[11px] text-red-300">
              {blocker}
            </p>
          ))}
          {pkg.warnings.map((warning) => (
            <p
              key={warning}
              className="flex items-start gap-1.5 text-[11px] text-amber-300"
            >
              <AlertTriangle size={11} className="mt-0.5 shrink-0" />
              {warning}
            </p>
          ))}
          {pkg.ready && (
            <dl className="grid gap-1 text-[11px] text-zinc-400 sm:grid-cols-2">
              <div>
                Title:{" "}
                <span className="text-zinc-200">{pkg.publish_title || "--"}</span>
              </div>
              <div>
                Series:{" "}
                <span className="text-zinc-200">{pkg.series_label || "--"}</span>
              </div>
              <div>
                Hashtags:{" "}
                <span className="text-zinc-200">
                  {pkg.publish_hashtags || "--"}
                </span>
              </div>
              <div>
                Length:{" "}
                <span className="text-zinc-200">
                  {pkg.duration_sec.toFixed(1)}s · {pkg.width}x{pkg.height}
                </span>
              </div>
            </dl>
          )}
        </div>
      )}
      {packageQ.isError && (
        <p role="alert" className="text-[11px] text-red-300">
          {toAIError(packageQ.error).detail}
        </p>
      )}
    </section>
  );
}
