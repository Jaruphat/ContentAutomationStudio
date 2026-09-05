/* ──────────────────────────────────────────────────────────────────────────
   PremiseBoard -- what to make next, screened before it costs an hour of GPU.

   One gate outranks the scores, the same way the two-second question does at
   the other end of the pipeline: an episode must be able to say, in one
   sentence, what the one strange thing is. A premise that cannot does not
   become a better film with better production, so it is refused before it is
   scored - and refusing it here costs a minute instead of an hour of
   rendering.

   Rejections stay on the board. The record of what was considered is the only
   thing that stops the same idea being re-proposed every month.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lightbulb, Loader2, Play, Plus, X } from "lucide-react";
import api from "../api/client";
import ActionError from "./ActionError";
import { useAppDispatch } from "../store/useProjectStore";
import type { Channel } from "../types";

export default function PremiseBoard({ channel }: { channel: Channel }) {
  const qc = useQueryClient();
  const dispatch = useAppDispatch();
  const [title, setTitle] = useState("");
  const [logline, setLogline] = useState("");
  const [strange, setStrange] = useState("");
  const [pillar, setPillar] = useState("");
  const [hook, setHook] = useState("");
  const [scores, setScores] = useState<Record<string, number>>({});

  const rubricQ = useQuery({
    queryKey: ["premise-rubric"],
    queryFn: api.premises.rubric,
    staleTime: Infinity,
  });
  const listQ = useQuery({
    queryKey: ["premises", channel.id],
    queryFn: () => api.premises.list(channel.id),
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["premises", channel.id] });

  const create = useMutation({
    mutationFn: () =>
      api.premises.create(channel.id, {
        title,
        logline,
        one_strange_thing: strange,
        pillar,
        hook_type: hook,
        scores,
      }),
    onSuccess: () => {
      setTitle("");
      setLogline("");
      setStrange("");
      setScores({});
      refresh();
    },
  });

  const start = useMutation({
    mutationFn: (premiseId: string) => api.premises.start(channel.id, premiseId),
    onSuccess: (project) => {
      dispatch({ type: "SET_PROJECT", id: project.id });
      refresh();
    },
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.premises.reject(channel.id, id, reason),
    onSuccess: refresh,
  });

  const rubric = rubricQ.data ?? [];

  return (
    <section className="space-y-3 border-t border-zinc-800 pt-3">
      <div className="flex items-center gap-2">
        <Lightbulb size={14} className="text-amber-400" />
        <h4 className="text-xs font-semibold uppercase text-zinc-300">
          Premises
        </h4>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-xs text-zinc-400">
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-sm"
            placeholder="The 3:17 Train"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Logline
          <input
            value={logline}
            onChange={(e) => setLogline(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-sm"
          />
        </label>
      </div>

      <label className="block text-xs text-zinc-400">
        The one strange thing
        <textarea
          rows={2}
          value={strange}
          onChange={(e) => setStrange(e.target.value)}
          className="mt-1 w-full rounded px-2 py-1 text-sm"
          placeholder="A train that should not exist keeps a timetable."
        />
        <span className="mt-0.5 block text-[10px] text-zinc-500">
          In one sentence. A premise that cannot answer this is refused before
          it is scored - it does not become a better film with better
          production, and rejecting it here costs a minute instead of an hour
          of rendering.
        </span>
      </label>

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs text-zinc-400">
          Pillar
          <select
            value={pillar}
            onChange={(e) => setPillar(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-sm"
          >
            <option value="">Unclassified</option>
            {(channel.pillars ?? []).map((entry) => (
              <option key={entry.key} value={entry.key}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zinc-400">
          Hook
          <select
            value={hook}
            onChange={(e) => setHook(e.target.value)}
            className="mt-1 w-full rounded px-2 py-1 text-sm"
          >
            <option value="">Unclassified</option>
            {(channel.hooks ?? []).map((entry) => (
              <option key={entry.key} value={entry.key}>
                {entry.key} · {entry.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Weighted, because an unweighted rubric ranks a premise that is easy
          to automate above one anybody would watch. */}
      <div className="space-y-2">
        {rubric.map((criterion) => (
          <label key={criterion.key} className="block text-xs text-zinc-400">
            <span className="flex flex-wrap items-baseline gap-2">
              <span className="font-medium text-zinc-300">{criterion.label}</span>
              <span className="text-[10px] text-zinc-500">
                weight {Math.round(criterion.weight * 100)}%
              </span>
            </span>
            <span className="mt-0.5 block text-[10px] leading-snug text-zinc-500">
              {criterion.question}
            </span>
            <input
              type="number"
              min={1}
              max={10}
              value={scores[criterion.key] ?? ""}
              onChange={(e) =>
                setScores((current) => ({
                  ...current,
                  [criterion.key]: Number(e.target.value),
                }))
              }
              className="mt-1 w-20 rounded px-2 py-1 text-sm"
            />
          </label>
        ))}
      </div>

      <button
        type="button"
        onClick={() => create.mutate()}
        disabled={create.isPending || !title.trim()}
        className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {create.isPending ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <Plus size={12} />
        )}
        Score this premise
      </button>
      <ActionError label="Score premise" error={create.error} />
      <ActionError label="Start episode" error={start.error} />

      <ul className="space-y-1">
        {(listQ.data ?? []).map((premise) => (
          <li
            key={premise.id}
            className={`flex flex-wrap items-center gap-2 rounded border px-2 py-1.5 text-xs ${
              premise.status === "rejected"
                ? "border-zinc-800 text-zinc-500"
                : "border-zinc-700 text-zinc-300"
            }`}
          >
            <span className="font-semibold text-zinc-200">
              {premise.total.toFixed(0)}
            </span>
            <span>{premise.title}</span>
            {premise.pillar && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px]">
                {premise.pillar}
              </span>
            )}
            {premise.status !== "candidate" && (
              <span className="text-[10px] uppercase">{premise.status}</span>
            )}
            {premise.rejection_reason && (
              <span className="text-[10px]">{premise.rejection_reason}</span>
            )}
            <span className="flex-1" />
            {premise.status === "candidate" && (
              <>
                <button
                  type="button"
                  onClick={() => start.mutate(premise.id)}
                  className="flex items-center gap-1 rounded bg-emerald-700 px-2 py-1 text-[11px] text-white"
                >
                  <Play size={10} />
                  Make it
                </button>
                <button
                  type="button"
                  onClick={() =>
                    reject.mutate({ id: premise.id, reason: "not this round" })
                  }
                  className="rounded p-1 text-zinc-500 hover:bg-zinc-800"
                  aria-label="Reject"
                >
                  <X size={12} />
                </button>
              </>
            )}
          </li>
        ))}
        {listQ.data?.length === 0 && (
          <li className="text-[11px] text-zinc-500">
            No premises yet. Every one that gets past this screen costs about an
            hour of rendering to find out about, which is what makes scoring
            them worth the minute.
          </li>
        )}
      </ul>
    </section>
  );
}
