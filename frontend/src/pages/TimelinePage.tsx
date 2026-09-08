/* ──────────────────────────────────────────────────────────────────────────
   TimelinePage -- Timeline of approved takes, plus the render plan and the
   actual FFmpeg review render.
   ────────────────────────────────────────────────────────────────────────── */

import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Film,
  Loader2,
  PlayCircle,
  ListOrdered,
  AlertCircle,
  Clock,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Terminal,
  AlertTriangle,
  Clapperboard,
  CheckCircle2,
  XCircle,
  Volume2,
} from "lucide-react";
import api, { toAIError } from "../api/client";
import {
  DEFAULT_NARRATION_VOICE,
  NARRATION_VOICES,
  resolveNarrationVoice,
  type NarrationVoice,
} from "../narrationVoices";
import ActionError from "../components/ActionError";
import AspectOverrideBanner from "../components/AspectOverrideBanner";
import SoundCueList from "../components/SoundCueList";
import SubtitleSettingsSection from "../components/SubtitleSettingsSection";
import { useAppState } from "../store/useProjectStore";
import type {
  RenderedFilm,
  RenderPlan,
  RenderResult,
  TimelineCoverage,
  TimelineItem,
} from "../types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type ProjectScoped<T> = { projectId: string; data: T } | null;

export function currentProjectValue<T>(
  value: ProjectScoped<T>,
  currentProjectId: string | null,
): T | null {
  return value?.projectId === currentProjectId ? value.data : null;
}

// ── Timeline item row ────────────────────────────────────────────────────

/**
 * One clip in the cut, identified the way a person identifies it: the scene it
 * belongs to, what the shot is of, and the frame itself. The ids are still
 * available as a tooltip for anyone reconciling against an export.
 */
function TimelineRow({
  item, index, onMove, onTrim, canMoveUp, canMoveDown,
}: {
  item: TimelineItem;
  index: number;
  onMove: (direction: -1 | 1) => void;
  onTrim: (inPoint: number, outPoint: number) => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
}) {
  // The trim is held locally while it is being typed and committed on blur:
  // sending a request per keystroke would rewrite the whole manifest eight
  // times to change one number.
  const [inPoint, setInPoint] = useState(item.in_point_sec.toFixed(1));
  const [outPoint, setOutPoint] = useState(item.out_point_sec.toFixed(1));
  const commit = () => onTrim(parseFloat(inPoint) || 0, parseFloat(outPoint) || 0);

  return (
    <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2.5">
      {/* Order indicator */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-zinc-300">
        {index + 1}
      </div>

      {/* The frame this position places */}
      <div className="hidden h-12 w-[86px] shrink-0 overflow-hidden rounded bg-zinc-950 sm:block">
        {item.thumbnail_url ? (
          <img
            src={item.thumbnail_url}
            alt={`Frame for ${item.shot_name || "this shot"}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-[10px] text-zinc-500">
            No preview
          </div>
        )}
      </div>

      {/* Main info */}
      <div
        className="min-w-0 flex-1"
        title={`Shot ${item.shot_id ?? "--"} · Take ${item.take_id ?? "--"}`}
      >
        <p className="truncate text-[11px] text-zinc-500">
          {item.scene_title || "Unassigned scene"}
        </p>
        <p className="truncate text-sm font-medium text-zinc-200">
          {item.shot_name || `Shot ${item.shot_id?.slice(0, 8) ?? "--"}`}
        </p>
      </div>

      {item.waived && (
        <span className="shrink-0 rounded-full bg-amber-900/40 px-2 py-0.5 text-[10px] font-medium text-amber-300">
          Waived
        </span>
      )}

      {/* Duration */}
      <div className="flex shrink-0 items-center gap-1 text-xs text-zinc-400">
        <Clock size={12} />
        <span>{item.duration_sec.toFixed(1)}s</span>
      </div>

      {/* Trim. The cut is assembled from approved takes, but where a clip
          starts and stops inside its take is an editing decision, and it was
          only reachable by rewriting the manifest through the API. */}
      <div className="hidden shrink-0 items-center gap-1 text-[10px] text-zinc-500 md:flex">
        <input
          aria-label={`Clip ${index + 1} starts at`}
          value={inPoint}
          onChange={(e) => setInPoint(e.target.value)}
          onBlur={commit}
          className="w-12 rounded border border-zinc-700 bg-zinc-900 px-1 py-0.5 text-right text-zinc-200"
        />
        <span>-</span>
        <input
          aria-label={`Clip ${index + 1} ends at`}
          value={outPoint}
          onChange={(e) => setOutPoint(e.target.value)}
          onBlur={commit}
          className="w-12 rounded border border-zinc-700 bg-zinc-900 px-1 py-0.5 text-right text-zinc-200"
        />
        <span>s</span>
      </div>

      <div className="flex shrink-0 flex-col">
        <button
          aria-label={`Move clip ${index + 1} earlier`}
          disabled={!canMoveUp}
          onClick={() => onMove(-1)}
          className="text-zinc-500 hover:text-zinc-200 disabled:opacity-25"
        >
          <ChevronUp size={12} />
        </button>
        <button
          aria-label={`Move clip ${index + 1} later`}
          disabled={!canMoveDown}
          onClick={() => onMove(1)}
          className="text-zinc-500 hover:text-zinc-200 disabled:opacity-25"
        >
          <ChevronDown size={12} />
        </button>
      </div>

      {/* Transitions */}
      <div className="hidden shrink-0 items-center gap-1 text-[10px] text-zinc-500 lg:flex">
        <span className="uppercase">{item.transition_in}</span>
        <ArrowRight size={10} />
        <span className="uppercase">{item.transition_out}</span>
      </div>
    </div>
  );
}

// ── Coverage: what the build left out ────────────────────────────────────

/**
 * A build that places 13 of 18 shots and says nothing about the other five
 * reads as a complete cut. This is the difference between the two.
 */
function CoveragePanel({ coverage }: { coverage: TimelineCoverage }) {
  if (coverage.missing.length === 0) return null;

  return (
    <section
      aria-label="Shots not on the timeline"
      className="rounded-lg border border-amber-800/60 bg-amber-900/15 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <AlertTriangle size={15} className="shrink-0 text-amber-400" />
          <h3 className="text-sm font-semibold text-amber-200">
            {coverage.covered_shots} of {coverage.total_shots} shots are on the
            timeline
          </h3>
        </div>
        <Link
          to="/review"
          className="rounded-md border border-amber-700 px-3 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-900/40"
        >
          Go to Review
        </Link>
      </div>

      <ul className="mt-3 space-y-1.5">
        {coverage.missing.map((entry) => (
          <li
            key={entry.shot_id}
            className="rounded-md bg-zinc-900/60 px-3 py-2 text-xs"
          >
            <p className="text-zinc-500">{entry.scene_title}</p>
            <p className="font-medium text-zinc-200">{entry.shot_name}</p>
            <p className="mt-0.5 text-amber-200/90">{entry.reason}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── Render plan display ──────────────────────────────────────────────────

function RenderPlanPanel({ plan }: { plan: RenderPlan }) {
  const segments = plan.timeline_items;
  const totalDuration = segments.reduce((sum, s) => sum + s.duration_sec, 0);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Terminal size={14} className="text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Render Plan</h3>
      </div>

      <div className="flex gap-4 text-xs">
        <span className="text-zinc-500">
          Total duration:{" "}
          <span className="text-zinc-300">{totalDuration.toFixed(1)}s</span>
        </span>
        <span className="text-zinc-500">
          Segments: <span className="text-zinc-300">{segments.length}</span>
        </span>
        <span className="text-zinc-500">
          FFmpeg:{" "}
          <span
            className={plan.ffmpeg_available ? "text-green-400" : "text-red-400"}
          >
            {plan.ffmpeg_available ? "Available" : "Not found"}
          </span>
        </span>
      </div>

      {!plan.ffmpeg_available && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-900/20 border border-yellow-800/50 px-3 py-2 text-xs text-yellow-300">
          <AlertTriangle size={13} />
          FFmpeg is not installed or not on PATH. The commands below are shown
          for reference but cannot be executed here.
        </div>
      )}

      {plan.warnings.map((warning, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-md border border-amber-800/50 bg-amber-900/20 px-3 py-2 text-xs text-amber-300"
        >
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{warning}</span>
        </div>
      ))}

      {plan.commands.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            FFmpeg Commands
          </h4>
          <div className="max-h-48 overflow-y-auto rounded-md bg-zinc-950 p-3">
            {plan.commands.map((cmd, i) => (
              <pre
                key={i}
                className="text-[11px] text-zinc-400 font-mono whitespace-pre-wrap mb-2 last:mb-0"
              >
                $ {cmd}
              </pre>
            ))}
          </div>
        </div>
      )}

      {plan.commands.length === 0 && segments.length === 0 && (
        <p className="text-xs text-zinc-500 italic">
          No segments available. Build the timeline first with approved takes.
        </p>
      )}

      {segments.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Segments
          </h4>
          <div className="space-y-1">
            {segments.map((seg, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-md bg-zinc-800/50 px-3 py-1.5 text-xs"
              >
                <span className="font-mono text-zinc-500">#{seg.order}</span>
                <span className="text-zinc-300 truncate flex-1">
                  {seg.file_path || "no file"}
                </span>
                <span className="text-zinc-400">{seg.duration_sec}s</span>
                <span className="text-zinc-500">
                  {seg.transition_in} / {seg.transition_out}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Render result display ────────────────────────────────────────────────

/** The finished film, played where it was made.
 *
 *  Every other stage of this application is reviewable in the browser except
 *  the one thing the pipeline exists to produce: the render returned an
 *  absolute path, the user left to find the file, and the path was gone on the
 *  next reload. This asks the server on load instead, so a film made overnight
 *  is on screen the next morning.
 *
 *  The aspect ratio comes from the file, not from a fixed box: a 576x1024
 *  vertical cartoon in a 16:9 frame is mostly black. */
function FinishedFilmPanel({ film }: { film: RenderedFilm }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <PlayCircle size={14} className="text-emerald-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Finished Film</h3>
        {film.rendered && (
          <span className="text-[11px] text-zinc-500">
            {film.width}x{film.height} · {film.duration_sec.toFixed(1)}s ·{" "}
            {formatBytes(film.size_bytes)}
            {film.has_audio ? " · with audio" : " · silent"}
          </span>
        )}
      </div>

      {!film.rendered && <p className="text-xs text-zinc-500">{film.reason}</p>}

      {film.rendered && (
        <>
          {film.stale && (
            <p className="rounded border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
              This film is older than the timeline on screen, so it is out of
              date - you would be reviewing a previous cut. Render Review again
              to see the current one.
            </p>
          )}
          <video
            controls
            preload="metadata"
            src={film.url}
            className="w-full max-h-[70vh] rounded-md bg-black"
            style={
              film.width && film.height
                ? { aspectRatio: `${film.width} / ${film.height}` }
                : undefined
            }
          />
          <p className="text-[11px] text-zinc-500">
            Rendered {new Date(film.rendered_at).toLocaleString()}.{" "}
            <a
              href={film.url}
              download
              className="text-indigo-400 hover:underline"
            >
              Download
            </a>
          </p>
        </>
      )}
    </div>
  );
}

function RenderResultPanel({ result }: { result: RenderResult }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Clapperboard size={14} className="text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Review Render</h3>
      </div>

      {/* What was delivered, and whether it met the spec it was delivered
          under. The same waiver the manifest carries. */}
      <AspectOverrideBanner
        warnings={result.warning_metadata}
        validation={result.delivery_validation}
      />

      <div
        className={`flex items-start gap-2 rounded-md px-3 py-2 text-sm font-medium ${
          result.rendered
            ? "bg-green-900/30 text-green-300"
            : "bg-red-900/30 text-red-300"
        }`}
      >
        {result.rendered ? (
          <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
        ) : (
          <XCircle size={14} className="mt-0.5 shrink-0" />
        )}
        <span>
          {result.rendered
            ? `Rendered ${result.segment_count} segment(s)`
            : result.reason}
        </span>
      </div>

      {result.rendered && (
        <>
          <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
            <span>
              Format:{" "}
              <span className="text-zinc-300">
                {result.width}x{result.height} {result.codec}
              </span>
            </span>
            <span>
              Duration:{" "}
              <span className="text-zinc-300">
                {result.duration_sec.toFixed(1)}s
              </span>
            </span>
            <span>
              Size:{" "}
              <span className="text-zinc-300">
                {formatBytes(result.size_bytes)}
              </span>
            </span>
          </div>
          <div className="rounded-md bg-zinc-950 px-3 py-2">
            <p className="text-[11px] font-mono text-zinc-400 break-all">
              {result.output_path}
            </p>
          </div>
        </>
      )}

      {result.warnings.map((warning, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-md border border-amber-800/50 bg-amber-900/20 px-3 py-2 text-xs text-amber-300"
        >
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{warning}</span>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// TimelinePage
// ══════════════════════════════════════════════════════════════════════════

export default function TimelinePage() {
  const { currentProjectId } = useAppState();
  const currentProjectRef = useRef(currentProjectId);
  currentProjectRef.current = currentProjectId;
  const qc = useQueryClient();
  const [scopedRenderPlan, setScopedRenderPlan] = useState<ProjectScoped<RenderPlan>>(null);
  const [scopedRenderResult, setScopedRenderResult] = useState<ProjectScoped<RenderResult>>(null);
  const renderPlan = currentProjectValue(scopedRenderPlan, currentProjectId);
  const renderResult = currentProjectValue(scopedRenderResult, currentProjectId);

  const timelineQ = useQuery({
    queryKey: ["timeline", currentProjectId],
    queryFn: () => api.timeline.get(currentProjectId!),
    enabled: !!currentProjectId,
  });

  const buildMut = useMutation({
    mutationFn: (projectId: string) => api.timeline.build(projectId),
    onSuccess: (_data, projectId) => {
      qc.invalidateQueries({ queryKey: ["timeline", projectId] });
      // A rebuilt cut can place different takes at different durations; a
      // render plan or result computed from the old cut must not linger and
      // be mistaken for a description of the new one.
      setScopedRenderPlan((value) => value?.projectId === projectId ? null : value);
      setScopedRenderResult((value) => value?.projectId === projectId ? null : value);
    },
  });

  const renderPlanMut = useMutation({
    mutationFn: (projectId: string) => api.timeline.renderPlan(projectId),
    onSuccess: (data, projectId) => {
      if (currentProjectRef.current === projectId) {
        setScopedRenderPlan({ projectId, data });
      }
    },
  });

  // Off by default: speaking a film takes time and is a choice, not a default.
  const [narrate, setNarrate] = useState(false);
  // The local voice costs nothing and cannot be directed; the hosted one is
  // metered and takes the channel's reading direction. Defaulting to the free
  // one keeps an overnight render from quietly spending.
  const [voiceProvider, setVoiceProvider] = useState<"system" | "openai">("system");
  // The render has always taken a voice name and the page never sent one, so
  // every episode was read by the default whatever was on screen.
  const [voice, setVoice] = useState<NarrationVoice>(DEFAULT_NARRATION_VOICE);
  // A video model writes its own soundtrack along with the picture - room
  // tone, footsteps, invented speech - and ducking that under a narrator
  // leaves two soundtracks arguing. On by default with narration, because a
  // narrated film almost never wants what the takes came with.
  const [narrationOnly, setNarrationOnly] = useState(true);
  // Choosing from a list of names is choosing blind. This episode was re-read,
  // re-cut and re-rendered twice before anyone could hear that the new voice
  // was barely different from the old one.
  const auditionRef = useRef<HTMLAudioElement | null>(null);
  const audition = useMutation({
    mutationFn: async (name: NarrationVoice) => {
      const clip = await api.timeline.previewVoice(
        currentProjectId as string,
        name,
      );
      auditionRef.current?.pause();
      const player = new Audio(URL.createObjectURL(clip));
      auditionRef.current = player;
      // The object URL is only needed until the clip has been decoded.
      player.addEventListener("ended", () => URL.revokeObjectURL(player.src));
      await player.play();
    },
  });
  // Asked on load, so a film rendered in a previous session is on screen
  // rather than living only in the response that produced it.
  const filmQ = useQuery({
    queryKey: ["rendered-film", currentProjectId],
    queryFn: () => api.timeline.latestRender(currentProjectId as string),
    enabled: Boolean(currentProjectId),
  });

  const renderMut = useMutation({
    mutationFn: (projectId: string) =>
      api.timeline.render(
        projectId,
        narrate,
        voiceProvider,
        voiceProvider === "openai" ? voice : "",
        narrate && narrationOnly,
      ),
    onSuccess: (data, projectId) => {
      if (currentProjectRef.current === projectId) {
        setScopedRenderResult({ projectId, data });
      }
      // The player reads from the server, not from this response, so a film
      // rendered now and one rendered last night reach the page the same way.
      qc.invalidateQueries({ queryKey: ["rendered-film", projectId] });
    },
  });

  const items = timelineQ.data?.items ?? [];
  const ordered = [...items].sort((a, b) => a.order - b.order);

  // The whole manifest is sent back, because that is what the endpoint takes
  // and because a cut is an ordered whole: half an edit applied is two clips
  // claiming the same position.
  const editMut = useMutation({
    mutationFn: (next: TimelineItem[]) =>
      api.timeline.update(
        currentProjectId as string,
        next.map((item, order) => ({
          shot_id: item.shot_id,
          take_id: item.take_id,
          order,
          in_point_sec: item.in_point_sec,
          out_point_sec: item.out_point_sec,
          duration_sec: item.duration_sec,
          transition_in: item.transition_in,
          transition_out: item.transition_out,
        })),
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["timeline", currentProjectId] }),
  });

  const moveItem = (index: number, direction: -1 | 1) => {
    const next = [...ordered];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    editMut.mutate(next);
  };

  const trimItem = (index: number, inPoint: number, outPoint: number) => {
    const current = ordered[index];
    if (current.in_point_sec === inPoint && current.out_point_sec === outPoint) return;
    const next = [...ordered];
    next[index] = {
      ...current,
      in_point_sec: inPoint,
      out_point_sec: outPoint,
      // The length of a clip is the piece of it that is used, so a trim that
      // did not change the duration would be a trim that changes nothing.
      duration_sec: Math.max(0, outPoint - inPoint),
    };
    editMut.mutate(next);
  };

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <Film size={32} className="mb-3 text-zinc-500" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  const totalDuration = timelineQ.data?.total_duration_sec ?? 0;
  const coverage = timelineQ.data?.coverage;
  const loadError = timelineQ.isError ? toAIError(timelineQ.error).detail : null;
  // The one refusal the user can clear from this page: the cut references
  // takes that no longer match their shots, so it has to be rebuilt.
  const staleLineage = !!loadError && loadError.includes("lineage");

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Film size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Timeline</h1>
          {items.length > 0 && (
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
              {items.length} item{items.length !== 1 ? "s" : ""} --{" "}
              {totalDuration.toFixed(1)}s
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => buildMut.mutate(currentProjectId)}
            disabled={buildMut.isPending}
            className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {buildMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <ListOrdered size={14} />
            )}
            Build Timeline
          </button>
          <button
            onClick={() => renderPlanMut.mutate(currentProjectId)}
            disabled={renderPlanMut.isPending}
            className="flex items-center gap-1.5 rounded-md border border-zinc-700 px-4 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {renderPlanMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <PlayCircle size={14} />
            )}
            Render Plan
          </button>
          <label
            title="Speak each shot's dialogue over the film, using this machine's own voice"
            className="flex items-center gap-1.5 text-xs text-zinc-400"
          >
            <input
              type="checkbox"
              checked={narrate}
              onChange={(event) => setNarrate(event.target.checked)}
            />
            Narrate
          </label>
          {narrate && (
            <select
              value={voiceProvider}
              onChange={(e) =>
                setVoiceProvider(e.target.value as "system" | "openai")
              }
              title={
                voiceProvider === "openai"
                  ? "Metered. Reads with the channel's voice direction."
                  : "This machine's own voice. Free, and cannot be directed."
              }
              className="h-8 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-xs text-zinc-300"
            >
              <option value="system">System voice (free)</option>
              <option value="openai">OpenAI voice (metered)</option>
            </select>
          )}
          {narrate && voiceProvider === "openai" && (
            <select
              aria-label="Narrator voice"
              value={voice}
              onChange={(e) => setVoice(resolveNarrationVoice(e.target.value))}
              title="Which of the provider's voices reads the film. How it reads - age, energy, pace - comes from the channel's voice direction."
              className="h-8 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-xs text-zinc-300"
            >
              {NARRATION_VOICES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          {narrate && (
            <label
              title="Drop the audio the takes came with and keep only the narration"
              className="flex items-center gap-1.5 text-xs text-zinc-400"
            >
              <input
                type="checkbox"
                checked={narrationOnly}
                onChange={(event) => setNarrationOnly(event.target.checked)}
              />
              Voice only
            </label>
          )}
          {narrate && voiceProvider === "openai" && (
            <button
              type="button"
              onClick={() => audition.mutate(voice)}
              disabled={audition.isPending || !currentProjectId}
              title="Read one line of this film in this voice, with the channel's direction, so you can hear it before rendering"
              className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-700 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              {audition.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Volume2 size={12} />
              )}
              Hear it
            </button>
          )}
          <button
            onClick={() => renderMut.mutate(currentProjectId)}
            disabled={renderMut.isPending || items.length === 0}
            title={
              items.length === 0
                ? "Build the timeline from approved takes first"
                : "Assemble the approved takes into a review video"
            }
            className="flex items-center gap-1.5 rounded-md bg-emerald-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {renderMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Clapperboard size={14} />
            )}
            Render Review
          </button>
        </div>
      </div>

      <ActionError label="Preview voice" error={audition.error} />

      {timelineQ.data && (
        <AspectOverrideBanner
          warnings={timelineQ.data.warnings}
          validation={timelineQ.data.delivery_validation}
        />
      )}

      {/* A refused read must never look like an empty cut. */}
      {loadError && (
        <section
          role="alert"
          aria-label="Timeline unavailable"
          className="rounded-lg border border-red-800 bg-red-900/25 p-4"
        >
          <div className="flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-red-200">
                The timeline could not be loaded
              </h2>
              <p className="text-sm text-red-200/90">{loadError}</p>
              {staleLineage && (
                <p className="text-xs text-red-200/70">
                  The stored cut points at takes that no longer match their
                  shots. Rebuilding replaces it with the takes that are
                  approved and current right now; nothing else is changed.
                </p>
              )}
              <button
                onClick={() => buildMut.mutate(currentProjectId)}
                disabled={buildMut.isPending}
                className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {buildMut.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <ListOrdered size={14} />
                )}
                Rebuild timeline
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Action failures, with the reason the backend gave. */}
      <ActionError label="Build timeline" error={buildMut.error} />
      <ActionError label="Render plan" error={renderPlanMut.error} />
      <ActionError label="Render review" error={renderMut.error} />

      {/* Loading */}
      {timelineQ.isLoading && (
        <div className="flex items-center gap-2 py-12 text-zinc-500 justify-center">
          <Loader2 size={14} className="animate-spin" /> Loading timeline...
        </div>
      )}

      {coverage && <CoveragePanel coverage={coverage} />}

      {/* Empty */}
      {timelineQ.data && items.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Film size={28} className="mb-2 text-zinc-500" />
          <p className="text-sm text-zinc-500">
            {buildMut.isSuccess
              ? "The build ran and found no shot with a current approved take, so the timeline is empty."
              : "No timeline items yet. Approve takes in Review, then click \"Build Timeline\" to assemble the sequence."}
          </p>
        </div>
      )}

      {/* Timeline list */}
      {items.length > 0 && (
        <>
          <div className="space-y-2">
            {ordered.map((item, i) => (
              <TimelineRow
                key={item.id}
                item={item}
                index={i}
                canMoveUp={i > 0}
                canMoveDown={i < ordered.length - 1}
                onMove={(direction) => moveItem(i, direction)}
                onTrim={(inPoint, outPoint) => trimItem(i, inPoint, outPoint)}
              />
            ))}
          </div>

          {/* Where this stage leads. */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3">
            <p className="text-xs text-zinc-500">
              Render a review video from these {items.length} clip
              {items.length === 1 ? "" : "s"}, or take the manifest and
              storyboard to Export.
            </p>
            <Link
              to="/export"
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
            >
              Go to Export
            </Link>
          </div>
        </>
      )}

      {/* Sound design belongs beside the cut it is timed to: a cue is placed
          inside a shot, and the shot's position is what the offset is measured
          from. */}
      {/* How the spoken lines are drawn on the picture. It lives here because
          captions are burned at render, and it lived nowhere at all until a
          Thai-language prototype needed a font with Thai glyphs: the component
          and its tests existed, and no page mounted it. */}
      <SubtitleSettingsSection projectId={currentProjectId} />

      <SoundCueList
        projectId={currentProjectId}
        shots={items
          .filter((item) => item.shot_id)
          .map((item) => ({
            id: item.shot_id as string,
            label: `${item.order + 1}. ${item.shot_name || "shot"}`,
          }))}
      />

      {/* Render output */}
      {filmQ.data && <FinishedFilmPanel film={filmQ.data} />}
      {renderResult && <RenderResultPanel result={renderResult} />}
      {renderPlan && <RenderPlanPanel plan={renderPlan} />}
    </div>
  );
}
