import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import api, { toAIError } from "../api/client";

/**
 * What the episode actually did, typed in from the platform.
 *
 * The channel page compares episodes and refuses to rank them below three per
 * pillar. It was comparing numbers that no page could enter: the capture
 * endpoint existed and nothing called it, so the learning loop ended at
 * "record your analytics" with nowhere to record them.
 *
 * Every field is optional on purpose. A capture taken a day after publishing
 * has views and little else; one taken a week later has retention. A form that
 * demanded all of them would be filled with zeroes, and a zero is a
 * measurement.
 */

const COUNTS: Array<[string, string]> = [
  ["views_24h", "Views (24h)"],
  ["views_7d", "Views (7d)"],
  ["impressions", "Impressions"],
  ["engaged_views", "Engaged views"],
  ["likes", "Likes"],
  ["comments", "Comments"],
  ["shares", "Shares"],
  ["subscribers_gained", "Subscribers gained"],
];

const RATES: Array<[string, string]> = [
  ["avg_percent_viewed", "Average viewed (%)"],
  ["chose_to_view_percent", "Chose to view (%)"],
  ["avg_view_duration_sec", "Average view (sec)"],
];

export default function AnalyticsCapture({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");

  const record = useMutation({
    mutationFn: () => {
      // Blank means "not measured", which is not the same as zero, so an empty
      // field is left out of the request rather than sent as 0.
      const body: Record<string, number | string> = { source: "manual" };
      for (const [field] of [...COUNTS, ...RATES]) {
        const raw = (values[field] ?? "").trim();
        if (raw !== "") body[field] = Number(raw);
      }
      if (notes.trim()) body.notes = notes.trim();
      return api.analytics.record(projectId, body);
    },
    onSuccess: () => {
      setValues({});
      setNotes("");
      qc.invalidateQueries({ queryKey: ["channel-analytics"] });
    },
  });

  const set = (field: string) => (raw: string) =>
    setValues((current) => ({ ...current, [field]: raw }));

  const anything = Object.values(values).some((raw) => raw.trim() !== "");
  const box = "w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100";

  return (
    <section
      aria-label="Record what this episode did"
      className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4"
    >
      <div className="flex items-center gap-2">
        <BarChart3 size={15} className="text-indigo-400" />
        <h2 className="text-sm font-semibold text-zinc-100">
          Record what this episode did
        </h2>
      </div>
      <p className="text-[11px] text-zinc-500">
        Read off the platform and typed in. Leave a field blank when you have
        not measured it - blank means unmeasured, and zero means zero. Captures
        accumulate, so a reading at a day and another at a week are two
        captures rather than an edit.
      </p>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[...COUNTS, ...RATES].map(([field, label]) => (
          <label key={field} className="block text-[10px] uppercase text-zinc-500">
            {label}
            <input
              aria-label={label}
              inputMode="decimal"
              value={values[field] ?? ""}
              onChange={(e) => set(field)(e.target.value)}
              className={box}
            />
          </label>
        ))}
      </div>

      <label className="block text-[10px] uppercase text-zinc-500">
        Notes
        <input
          aria-label="Analytics notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="posted late, thumbnail changed on day two..."
          className={box}
        />
      </label>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => record.mutate()}
          disabled={!anything || record.isPending}
          className="rounded bg-zinc-800 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          {record.isPending ? "Recording…" : "Record capture"}
        </button>
        {record.isSuccess && (
          <span role="status" className="text-[11px] text-emerald-400">
            Capture recorded.
          </span>
        )}
      </div>
      {record.isError && (
        <p role="alert" className="text-[11px] text-red-300">
          {toAIError(record.error).detail}
        </p>
      )}
    </section>
  );
}
