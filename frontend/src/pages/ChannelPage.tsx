/* ──────────────────────────────────────────────────────────────────────────
   Channel -- the thing that outlives an episode.

   A project is one film. The house look, the negative prompt, the narrator,
   the audience and the content pillars are the same for every episode, and
   re-entering them per episode is both tedious and how a channel stops
   looking like one channel.

   Starting an episode here copies the bibles into the new project. Copied,
   not referenced: revising the look must not rewrite a film that was already
   delivered under the old one.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Loader2, Plus, Radio, Save } from "lucide-react";
import api, { toAIError } from "../api/client";
import ActionError from "../components/ActionError";
import ChannelAnalytics from "../components/ChannelAnalytics";
import PremiseBoard from "../components/PremiseBoard";
import { useAppDispatch } from "../store/useProjectStore";
import type { Channel, ChannelVocabularyEntry } from "../types";

/** Pillars and hooks are edited as one line each: `key | name | purpose`.
 *  A grid of inputs for a three-row vocabulary is more chrome than content,
 *  and this keeps the key visible - which is the part that has to match what
 *  the analytics grouping will later count. */
function parseVocabulary(text: string): ChannelVocabularyEntry[] {
  return text
    .split("\n")
    .map((line) => line.split("|").map((part) => part.trim()))
    .filter((parts) => parts[0])
    .map((parts) => ({
      key: parts[0],
      name: parts[1] || parts[0],
      purpose: parts[2] || "",
    }));
}

function formatVocabulary(entries: ChannelVocabularyEntry[]): string {
  return entries
    .map((entry) =>
      [entry.key, entry.name, entry.purpose || entry.example || ""]
        .filter(Boolean)
        .join(" | "),
    )
    .join("\n");
}

function Field({
  label,
  value,
  onChange,
  rows = 1,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  hint?: string;
}) {
  return (
    <label className="block text-xs text-zinc-400">
      {label}
      {rows > 1 ? (
        <textarea
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full rounded px-2 py-1 text-sm"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full rounded px-2 py-1 text-sm"
        />
      )}
      {hint && <span className="mt-0.5 block text-[10px] text-zinc-500">{hint}</span>}
    </label>
  );
}

function ChannelEditor({ channel }: { channel: Channel }) {
  const qc = useQueryClient();
  const dispatch = useAppDispatch();
  const [form, setForm] = useState({
    ...channel,
    pillarsText: formatVocabulary(channel.pillars ?? []),
    hooksText: formatVocabulary(channel.hooks ?? []),
  });
  const [episodeTitle, setEpisodeTitle] = useState("");
  const [pillar, setPillar] = useState("");
  const [hook, setHook] = useState("");
  const [premise, setPremise] = useState("");

  const set = (key: string) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const refresh = () => qc.invalidateQueries({ queryKey: ["channels"] });

  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.channels.remove(channel.id),
    onSuccess: () => {
      setConfirming(false);
      refresh();
    },
  });

  const save = useMutation({
    mutationFn: () =>
      api.channels.update(channel.id, {
        name: form.name,
        tagline: form.tagline,
        audience: form.audience,
        visual_style: form.visual_style,
        negative_prompt: form.negative_prompt,
        camera_language: form.camera_language,
        voice_direction: form.voice_direction,
        sound_direction: form.sound_direction,
        aspect_ratio: form.aspect_ratio,
        target_resolution: form.target_resolution,
        frame_rate: Number(form.frame_rate) || 30,
        target_duration_sec: Number(form.target_duration_sec) || 32,
        pillars: parseVocabulary(form.pillarsText),
        hooks: parseVocabulary(form.hooksText),
      }),
    onSuccess: refresh,
  });

  const episodesQ = useQuery({
    queryKey: ["channel-episodes", channel.id],
    queryFn: () => api.channels.episodes(channel.id),
  });

  const start = useMutation({
    mutationFn: () =>
      api.channels.startEpisode(channel.id, {
        title: episodeTitle,
        pillar,
        hook_type: hook,
        premise,
      }),
    onSuccess: (project) => {
      setEpisodeTitle("");
      setPremise("");
      qc.invalidateQueries({ queryKey: ["channel-episodes", channel.id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      dispatch({ type: "SET_PROJECT", id: project.id });
    },
  });

  const pillars = parseVocabulary(form.pillarsText);
  const hooks = parseVocabulary(form.hooksText);

  return (
    <article className="space-y-4 rounded-lg border border-zinc-700 bg-zinc-900/70 p-4">
      <div className="flex items-center gap-2">
        <Radio size={14} className="text-indigo-400" />
        <h3 className="font-semibold text-zinc-100">{channel.name}</h3>
        <span className="text-[11px] text-zinc-500">{channel.tagline}</span>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <Field label="Name" value={form.name} onChange={set("name")} />
        <Field label="Tagline" value={form.tagline} onChange={set("tagline")} />
        <Field label="Audience" value={form.audience} onChange={set("audience")} rows={2} />
        <Field
          label="Voice direction"
          value={form.voice_direction}
          onChange={set("voice_direction")}
          rows={2}
          hint="Read by the narration track when a real voice provider is configured."
        />
        <Field
          label="Visual bible"
          value={form.visual_style}
          onChange={set("visual_style")}
          rows={4}
          hint="Copied into every new episode's Style, so it reaches every prompt."
        />
        <Field
          label="Negative prompt"
          value={form.negative_prompt}
          onChange={set("negative_prompt")}
          rows={4}
          hint="What the look must never contain."
        />
        <Field
          label="Camera language"
          value={form.camera_language}
          onChange={set("camera_language")}
          rows={2}
        />
        <Field
          label="Sound direction"
          value={form.sound_direction}
          onChange={set("sound_direction")}
          rows={2}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <Field label="Aspect" value={form.aspect_ratio} onChange={set("aspect_ratio")} />
        <Field
          label="Resolution"
          value={form.target_resolution}
          onChange={set("target_resolution")}
        />
        <Field
          label="FPS"
          value={String(form.frame_rate)}
          onChange={set("frame_rate")}
        />
        <Field
          label="Length (sec)"
          value={String(form.target_duration_sec)}
          onChange={set("target_duration_sec")}
        />
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <Field
          label="Pillars"
          value={form.pillarsText}
          onChange={set("pillarsText")}
          rows={4}
          hint="One per line: key | name | purpose. The key is what analytics groups by, so it has to stay stable."
        />
        <Field
          label="Hooks"
          value={form.hooksText}
          onChange={set("hooksText")}
          rows={4}
          hint="One per line: key | name | example."
        />
      </div>

      <button
        type="button"
        onClick={() => save.mutate()}
        disabled={save.isPending || !form.name.trim()}
        className="flex items-center gap-1 rounded bg-zinc-700 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
        Save channel bibles
      </button>
      <ActionError label="Save channel" error={save.error} />

      {/* A channel that was tried once and abandoned otherwise stays in the
          list for ever, and its premises keep appearing in the board. */}
      {confirming ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
          Delete “{channel.name}” and its premises?
          <button
            type="button"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="rounded bg-red-700 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {remove.isPending ? "Deleting…" : "Delete channel"}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
          >
            Keep
          </button>
        </div>
      ) : (
        <button
          type="button"
          aria-label={`Delete channel ${channel.name}`}
          onClick={() => setConfirming(true)}
          className="text-xs text-zinc-500 hover:text-red-400"
        >
          Delete this channel
        </button>
      )}
      <ActionError label="Delete channel" error={remove.error} />

      <PremiseBoard channel={channel} />

      {/* -- Episodes ------------------------------------------------------ */}
      <section className="space-y-2 border-t border-zinc-800 pt-3">
        <h4 className="text-xs font-semibold uppercase text-zinc-300">
          Episodes
        </h4>
        <p className="text-[10px] text-zinc-500">
          Starting an episode copies this channel's bibles into a new project.
          Copied, not linked: revising the channel later never rewrites an
          episode that was already made under the old look.
        </p>

        <div className="grid gap-2 sm:grid-cols-4">
          <label className="text-xs text-zinc-400 sm:col-span-2">
            Episode title
            <input
              value={episodeTitle}
              onChange={(e) => setEpisodeTitle(e.target.value)}
              className="mt-1 w-full rounded px-2 py-1 text-sm"
              placeholder="The 3:17 Train"
            />
          </label>
          <label className="text-xs text-zinc-400">
            Pillar
            <select
              value={pillar}
              onChange={(e) => setPillar(e.target.value)}
              className="mt-1 w-full rounded px-2 py-1 text-sm"
            >
              <option value="">Unclassified</option>
              {pillars.map((entry) => (
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
              {hooks.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.key} · {entry.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Field label="Premise" value={premise} onChange={setPremise} rows={2} />
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending || !episodeTitle.trim()}
          className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {start.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Plus size={12} />
          )}
          Start episode
        </button>
        <ActionError label="Start episode" error={start.error} />

        <ul className="space-y-1">
          {(episodesQ.data ?? []).map((episode) => (
            <li
              key={episode.id}
              className="flex flex-wrap items-center gap-2 rounded border border-zinc-800 px-2 py-1.5 text-xs"
            >
              <span className="font-medium text-zinc-200">{episode.title}</span>
              {episode.pillar && (
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                  {episode.pillar}
                </span>
              )}
              {episode.hook_type && (
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                  {episode.hook_type}
                </span>
              )}
              <span className="flex-1" />
              <Link
                to="/storyboard"
                onClick={() =>
                  dispatch({ type: "SET_PROJECT", id: episode.id })
                }
                className="text-indigo-400 hover:underline"
              >
                Open
              </Link>
            </li>
          ))}
          {episodesQ.data?.length === 0 && (
            <li className="text-[11px] text-zinc-500">
              No episodes yet.
            </li>
          )}
        </ul>
      </section>

      <ChannelAnalytics channelId={channel.id} />
    </article>
  );
}

export default function ChannelPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const channelsQ = useQuery({ queryKey: ["channels"], queryFn: api.channels.list });

  const create = useMutation({
    mutationFn: () => api.channels.create({ name }),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["channels"] });
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
      <div className="flex items-center gap-3">
        <Radio size={20} className="text-indigo-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Channels</h1>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-zinc-400">
          New channel
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-64 rounded px-2 py-1 text-sm"
            placeholder="ODDVERSE"
          />
        </label>
        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={create.isPending || !name.trim()}
          className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          <Plus size={12} />
          Create
        </button>
      </div>
      <ActionError label="Create channel" error={create.error} />

      {channelsQ.isLoading && (
        <div className="flex items-center gap-2 py-8 text-zinc-500">
          <Loader2 size={14} className="animate-spin" /> Loading channels...
        </div>
      )}
      {channelsQ.isError && (
        <p role="alert" className="text-sm text-red-300">
          {toAIError(channelsQ.error).detail}
        </p>
      )}
      {channelsQ.data?.length === 0 && (
        <p className="text-sm text-zinc-500">
          No channels yet. A channel holds the look, the voice and the pillars
          that every episode shares, so the next episode does not start from a
          blank page.
        </p>
      )}

      <div className="space-y-4">
        {(channelsQ.data ?? []).map((channel) => (
          <ChannelEditor key={channel.id} channel={channel} />
        ))}
      </div>
    </div>
  );
}
