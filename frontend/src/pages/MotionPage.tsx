/* ──────────────────────────────────────────────────────────────────────────
   Motion -- approved pictures, given something to do.

   A still episode is finished at Review. A moving one has one more decision
   per shot, and it is a small one: this picture, for this long, doing this.

   Everything else that a clip needs is bookkeeping, and doing it by hand is
   four separate traps. A still and the clip made from it cannot be the same
   shot, because turning a shot into an image-to-video shot moves its content
   revision and puts the frame captured from its own still out of date. The
   still then has to come off the cut, or the film plays the picture and then
   the clip of it. The clip has to be told explicitly which frame it starts
   on. And the clips cannot exist before their stills are drawn, because
   Generate runs over every eligible shot and refuses the whole run for one
   that has no picture yet.

   None of that is a decision anybody wants to make twenty-eight times, so
   this page makes none of it visible: choose a picture, say what happens,
   press the button.
   ────────────────────────────────────────────────────────────────────────── */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Film, Loader2, Wand2 } from "lucide-react";
import api, { toAIError } from "../api/client";
import ActionError from "../components/ActionError";
import ImagePreview from "../components/ImagePreview";
import { useAppState } from "../store/useProjectStore";
import type { MotionCandidate, Workflow } from "../types";

/** How many frames a clip of this length costs, at the usual video rate. */
export const CLIP_FRAME_RATE = 24;

/**
 * Roughly how long this clip will take to generate.
 *
 * Measured on the workstation this was built on: a 124-frame clip took 220 to
 * 230 seconds, which is about 1.8 seconds of GPU per frame. It is an estimate
 * and says so - but a page that lets you queue twenty-eight clips without
 * mentioning that it is three hours of machine is a page that lies by
 * omission.
 */
export const GPU_SECONDS_PER_FRAME = 1.8;

export function estimateClipMinutes(durationSec: number): number {
  const frames = Math.max(1, Math.round(durationSec * CLIP_FRAME_RATE));
  return (frames * GPU_SECONDS_PER_FRAME) / 60;
}

/** "2 h 25 m", "18 m", "40 s" - whichever unit the number is actually in. */
export function humaniseMinutes(minutes: number): string {
  if (minutes < 1) return `${Math.max(1, Math.round(minutes * 60))} s`;
  if (minutes < 60) return `${Math.round(minutes)} m`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes - hours * 60);
  return rest ? `${hours} h ${rest} m` : `${hours} h`;
}

/**
 * The graphs that can actually make a clip, and which one to start on.
 *
 * Two of the registered image-to-video workflows are UI exports with no
 * parameter mapping: they cannot be sent a start frame, so offering them is
 * offering a button that fails. And a project with no default video workflow
 * left the picker on "Project default", which resolves to nothing and refuses
 * the request - a first press that could only fail.
 */
export function pickClipWorkflows(
  workflows: Workflow[],
  projectDefaultId: string,
): { options: Workflow[]; selected: string } {
  const options = workflows.filter(
    (workflow) =>
      workflow.purpose === "image-to-video"
      && Boolean((workflow.parameter_mapping ?? {}).referenceImage),
  );
  const preferred = options.some((workflow) => workflow.id === projectDefaultId)
    ? projectDefaultId
    : options[0]?.id ?? "";
  return { options, selected: preferred };
}

function CandidateRow({
  projectId,
  candidate,
  videoWorkflows,
  defaultWorkflowId,
}: {
  projectId: string;
  candidate: MotionCandidate;
  videoWorkflows: Workflow[];
  defaultWorkflowId: string;
}) {
  const qc = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(
    (candidate.planned_duration_sec || 5).toFixed(1),
  );
  const [workflowId, setWorkflowId] = useState(defaultWorkflowId);

  const animate = useMutation({
    mutationFn: () =>
      api.motion.animate(projectId, {
        take_id: candidate.take_id,
        video_prompt: prompt,
        duration_sec: Number(seconds) || 0,
        workflow_id: workflowId || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["motion", projectId] });
      qc.invalidateQueries({ queryKey: ["scenes", projectId] });
    },
  });

  const moving = Boolean(candidate.clip_shot_id);
  const cost = estimateClipMinutes(Number(seconds) || 0);

  return (
    <article className="flex flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 sm:flex-row">
      <div className="w-full shrink-0 sm:w-56">
        <ImagePreview
          src={candidate.take_url}
          alt={`Approved still for ${candidate.shot_label}`}
          className="h-32 w-full"
        />
        <p className="mt-1 truncate text-[11px] text-zinc-500">
          {candidate.shot_label}
        </p>
      </div>

      <div className="min-w-0 flex-1 space-y-2">
        {candidate.dialogue && (
          <p className="truncate text-xs text-zinc-400">“{candidate.dialogue}”</p>
        )}

        {moving ? (
          <p className="flex items-center gap-1.5 text-xs text-emerald-400">
            <Film size={13} />
            Moving · clip is {candidate.clip_status || "waiting"}
          </p>
        ) : (
          <>
            <label className="block text-xs text-zinc-400">
              What happens in the clip
              <textarea
                aria-label={`Motion for ${candidate.shot_label}`}
                rows={2}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="He turns the flower slowly in both hands. The camera holds still."
                className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
              />
              {/* The one thing that never works, said once, where it is used. */}
              <span className="mt-0.5 block text-[10px] text-zinc-500">
                Write what happens, not what must not: the model ignores
                prohibitions. Told to stay seated, it stood up and walked.
              </span>
            </label>

            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-zinc-400">
                Seconds
                <input
                  aria-label={`Clip seconds for ${candidate.shot_label}`}
                  value={seconds}
                  onChange={(event) => setSeconds(event.target.value)}
                  className="mt-1 w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
                />
              </label>
              <label className="min-w-0 flex-1 text-xs text-zinc-400">
                Workflow
                <select
                  aria-label={`Clip workflow for ${candidate.shot_label}`}
                  value={workflowId}
                  onChange={(event) => setWorkflowId(event.target.value)}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
                >
                  {videoWorkflows.map((workflow) => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={!prompt.trim() || animate.isPending}
                onClick={() => animate.mutate()}
                title={`About ${humaniseMinutes(cost)} of GPU`}
                className="flex h-8 items-center gap-1.5 rounded-md bg-indigo-600 px-3 text-xs font-medium text-white disabled:opacity-50"
              >
                {animate.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Wand2 size={13} />
                )}
                Animate
              </button>
              <span className="text-[11px] text-zinc-500">
                ≈ {humaniseMinutes(cost)} of GPU
              </span>
            </div>
          </>
        )}
        <ActionError label="Animate" error={animate.error} />
      </div>
    </article>
  );
}

export default function MotionPage() {
  const { currentProjectId } = useAppState();

  const candidatesQ = useQuery({
    queryKey: ["motion", currentProjectId],
    queryFn: () => api.motion.candidates(currentProjectId as string),
    enabled: Boolean(currentProjectId),
  });
  const workflowsQ = useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows.list,
  });
  const projectQ = useQuery({
    queryKey: ["project", currentProjectId],
    queryFn: () => api.projects.get(currentProjectId as string),
    enabled: Boolean(currentProjectId),
  });

  const { options: videoWorkflows, selected: defaultWorkflowId } = useMemo(
    () =>
      pickClipWorkflows(
        workflowsQ.data ?? [],
        projectQ.data?.default_video_workflow_id ?? "",
      ),
    [workflowsQ.data, projectQ.data?.default_video_workflow_id],
  );

  const rows = candidatesQ.data ?? [];
  const waiting = rows.filter((row) => !row.clip_shot_id);
  const pending = waiting.reduce(
    (sum, row) => sum + estimateClipMinutes(row.planned_duration_sec || 5),
    0,
  );

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <Clapperboard size={32} className="mb-3 text-zinc-500" />
        <h2 className="text-lg font-semibold text-zinc-300">No project selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Choose a project to give its approved pictures something to do.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-6 py-6">
      <div className="flex flex-wrap items-center gap-3">
        <Clapperboard size={20} className="text-indigo-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Motion</h1>
        {rows.length > 0 && (
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
            {rows.length - waiting.length} of {rows.length} moving
          </span>
        )}
      </div>

      <p className="max-w-2xl text-xs text-zinc-500">
        Every approved picture in this project. Animating one makes the clip
        that starts from it, takes the still off the cut, and leaves the film
        playing the clip. Nothing here changes a picture that has already been
        approved.
      </p>

      {videoWorkflows.length === 0 && (
        <p role="alert" className="text-xs text-amber-300">
          No image-to-video workflow is registered with a start-frame input, so
          nothing here can be animated yet. Import one under Workflows and map
          its reference image.
        </p>
      )}

      {waiting.length > 0 && (
        <p className="text-xs text-amber-300/80">
          Animating all {waiting.length} would be roughly{" "}
          {humaniseMinutes(pending)} of generation on this machine.
        </p>
      )}

      {candidatesQ.isLoading && (
        <p className="flex items-center gap-2 text-sm text-zinc-400">
          <Loader2 size={14} className="animate-spin" />
          Looking for approved pictures…
        </p>
      )}
      {candidatesQ.isError && (
        <p role="alert" className="text-sm text-red-300">
          {toAIError(candidatesQ.error).detail}
        </p>
      )}
      {candidatesQ.data?.length === 0 && (
        <p className="text-sm text-zinc-500">
          No approved pictures yet. Generate the shots and approve them in
          Review, and they will appear here.
        </p>
      )}

      <div className="space-y-3">
        {rows.map((candidate) => (
          <CandidateRow
            key={`${candidate.take_id}:${defaultWorkflowId}`}
            projectId={currentProjectId}
            candidate={candidate}
            videoWorkflows={videoWorkflows}
            defaultWorkflowId={defaultWorkflowId}
          />
        ))}
      </div>
    </div>
  );
}
