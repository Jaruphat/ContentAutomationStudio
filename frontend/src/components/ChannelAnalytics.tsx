/* ──────────────────────────────────────────────────────────────────────────
   ChannelAnalytics -- what the audience did, read against what we chose.

   The refusal is the feature. Three episodes per pillar cannot say which
   pillar wins, and neither can nine when eight are unpublished. A comparison
   that ranks anyway produces a winner, the winner gets scaled, and a month of
   work follows a number that was noise.

   So the verdict line is shown first and says plainly when it cannot name one,
   with the reason. The groups are underneath as numbers to look at, not as a
   result to act on.
   ────────────────────────────────────────────────────────────────────────── */

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Loader2 } from "lucide-react";
import api from "../api/client";

function verdictLine(winner: Record<string, unknown>, dimension: string) {
  const named = winner[dimension];
  return {
    named: typeof named === "string" && named.length > 0 ? named : null,
    reason: String(winner.reason ?? ""),
  };
}

export default function ChannelAnalytics({ channelId }: { channelId: string }) {
  const reportQ = useQuery({
    queryKey: ["channel-analytics", channelId],
    queryFn: () => api.analytics.channel(channelId),
  });

  if (reportQ.isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-xs text-zinc-500">
        <Loader2 size={12} className="animate-spin" /> Reading the numbers...
      </div>
    );
  }
  const report = reportQ.data;
  if (!report) return null;

  const pillar = verdictLine(report.winner, "pillar");
  const hook = verdictLine(report.winner_by_hook, "hook_type");

  return (
    <section className="space-y-3 border-t border-zinc-800 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <BarChart3 size={14} className="text-indigo-400" />
        <h4 className="text-xs font-semibold uppercase text-zinc-300">
          Analytics
        </h4>
        <span className="text-[11px] text-zinc-500">
          {report.episode_count} measured
          {report.unmeasured_count > 0 &&
            `, ${report.unmeasured_count} not published yet`}
          {" · ranked on "}
          {report.ranked_on.replace(/_/g, " ")}
        </span>
      </div>

      {/* The verdict, or the honest absence of one. */}
      {[
        { label: "Pillar", value: pillar },
        { label: "Hook", value: hook },
      ].map(({ label, value }) => (
        <p
          key={label}
          className={`rounded border px-3 py-2 text-[11px] leading-snug ${
            value.named
              ? "border-emerald-900/60 bg-emerald-950/30 text-emerald-200"
              : "border-zinc-800 bg-zinc-900/60 text-zinc-400"
          }`}
        >
          <span className="font-medium">{label}: </span>
          {value.named ? `${value.named} — ${value.reason}` : value.reason}
        </p>
      ))}

      {Object.entries(report.groups).map(([dimension, groups]) =>
        groups.length === 0 ? null : (
          <div key={dimension} className="space-y-1">
            <p className="text-[10px] uppercase text-zinc-500">
              {dimension.replace(/_/g, " ")}
            </p>
            {groups.map((group) => (
              <div
                key={group.value}
                className="flex flex-wrap items-center gap-2 rounded border border-zinc-800 px-2 py-1 text-xs text-zinc-300"
              >
                <span className="font-medium">{group.value}</span>
                <span className="text-zinc-500">
                  {group.avg_percent_viewed === null
                    ? "no retention recorded"
                    : `${group.avg_percent_viewed.toFixed(1)}% viewed`}
                </span>
                <span
                  className={`text-[10px] ${
                    group.sample_size < report.minimum_group_size
                      ? "text-amber-400"
                      : "text-zinc-500"
                  }`}
                  title={
                    group.sample_size < report.minimum_group_size
                      ? `Below ${report.minimum_group_size} episodes, so this is an anecdote rather than a result`
                      : ""
                  }
                >
                  n={group.sample_size}
                </span>
              </div>
            ))}
          </div>
        ),
      )}
    </section>
  );
}
