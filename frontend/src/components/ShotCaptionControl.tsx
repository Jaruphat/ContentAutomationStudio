import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { toAIError } from "../api/client";
import type { Shot } from "../types";

/** Three to six words on a card, per the channel's subtitle bible. */
const EMPHASIS_MAX_WORDS = 6;

/**
 * The two caption tracks, written where the shot is.
 *
 * The spoken line is captioned in full for accessibility; the emphasis card is
 * a separate, larger track held over the picture and read at a glance. Both
 * were script-only until now - two produced episodes had their cards typed
 * into a Python file, which is not a thing a person making a channel can do.
 *
 * Neither reaches a model. Saving them does not invalidate a clip already
 * generated, which is exactly why they are kept apart from the clip direction
 * beside them.
 */
export default function ShotCaptionControl({
  shot,
  projectId,
}: {
  shot: Shot;
  projectId: string;
}) {
  const [dialogue, setDialogue] = useState(shot.dialogue ?? "");
  const [emphasis, setEmphasis] = useState(shot.emphasis_text ?? "");
  const qc = useQueryClient();

  const save = useMutation({
    mutationFn: () =>
      api.shots.update(projectId, shot.scene_id, shot.id, {
        dialogue,
        emphasis_text: emphasis,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shot", projectId] });
      qc.invalidateQueries({ queryKey: ["shots", projectId] });
      qc.invalidateQueries({ queryKey: ["preflight", projectId] });
    },
  });

  const changed =
    dialogue !== (shot.dialogue ?? "") || emphasis !== (shot.emphasis_text ?? "");
  const cardWords = emphasis.replace(/\//g, " ").split(/\s+/).filter(Boolean).length;
  const box =
    "mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100";

  return (
    <div className="my-4 space-y-2 rounded border border-zinc-700 p-3">
      <p className="text-xs font-medium text-zinc-300">Captions</p>
      <label className="block text-xs text-zinc-400">
        Spoken line
        <textarea
          aria-label="Spoken line"
          rows={2}
          value={dialogue}
          onChange={(e) => setDialogue(e.target.value)}
          className={box}
        />
      </label>
      <label className="block text-xs text-zinc-400">
        Emphasis card
        <input
          aria-label="Emphasis card"
          value={emphasis}
          onChange={(e) => setEmphasis(e.target.value)}
          placeholder="A DOOR AT THE END."
          className={box}
        />
      </label>
      {cardWords > EMPHASIS_MAX_WORDS && (
        <p className="rounded border border-amber-900/60 bg-amber-950/30 p-1.5 text-[11px] leading-snug text-amber-200">
          {cardWords} words. A card is held over the picture and read at a
          glance — three to six. The full line is carried by the caption track
          above.
        </p>
      )}
      <p className="text-[11px] text-zinc-400">
        Neither is sent to a model, so saving these does not put a clip already
        generated for this shot out of date. Applies on the next render.
      </p>
      <button
        type="button"
        disabled={!changed || save.isPending}
        onClick={() => save.mutate()}
        className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 disabled:opacity-50"
      >
        {save.isPending ? "Saving…" : "Save captions"}
      </button>
      {save.isSuccess && (
        <p role="status" className="text-xs text-emerald-400">
          Saved. Render again to see them.
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-xs text-red-300">
          {toAIError(save.error).detail}
        </p>
      )}
    </div>
  );
}
