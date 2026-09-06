import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import api, { toAIError } from "../api/client";
import type { Scene } from "../types";

/**
 * A scene's own fields, editable.
 *
 * Until this existed a scene could be created and deleted and nothing else.
 * It arrived called "Scene 3" and stayed that way: the inspector showed its
 * title, summary, purpose, time of day, beat, duration, location and cast as
 * read-only text, and the only way to write any of them was to post to the
 * API. Two of them are not decoration - `time_of_day` and `summary` reach the
 * compiled prompt, so a scene nobody could edit was a prompt nobody could
 * correct except through a terminal.
 *
 * The cast and location are chosen from the story bible rather than typed,
 * because a scene naming a character who does not exist is a scene whose
 * prompt silently loses them.
 */

export default function SceneEditor({
  projectId,
  scene,
  onDone,
}: {
  projectId: string;
  scene: Scene;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(scene.title);
  const [purpose, setPurpose] = useState(scene.purpose);
  const [summary, setSummary] = useState(scene.summary);
  const [timeOfDay, setTimeOfDay] = useState(scene.time_of_day);
  const [beat, setBeat] = useState(scene.emotional_beat);
  const [duration, setDuration] = useState(String(scene.planned_duration_sec));
  const [locationId, setLocationId] = useState(scene.location_id ?? "");
  const [characterIds, setCharacterIds] = useState<string[]>(scene.character_ids ?? []);

  const charactersQ = useQuery({
    queryKey: ["characters", projectId],
    queryFn: () => api.characters.list(projectId),
  });
  const locationsQ = useQuery({
    queryKey: ["locations", projectId],
    queryFn: () => api.locations.list(projectId),
  });

  const save = useMutation({
    mutationFn: () =>
      api.scenes.update(projectId, scene.id, {
        title,
        purpose,
        summary,
        time_of_day: timeOfDay,
        emotional_beat: beat,
        planned_duration_sec: parseFloat(duration) || 0,
        location_id: locationId || null,
        character_ids: characterIds,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scenes", projectId] });
      qc.invalidateQueries({ queryKey: ["scene", projectId, scene.id] });
      onDone();
    },
  });

  const box = "w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100";

  return (
    <div className="space-y-2 border-t border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <label className="block text-[10px] uppercase text-zinc-500">
          Title
          <input
            aria-label="Scene title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={box}
          />
        </label>
        <label className="block text-[10px] uppercase text-zinc-500">
          Time of day
          <input
            aria-label="Scene time of day"
            value={timeOfDay}
            onChange={(e) => setTimeOfDay(e.target.value)}
            placeholder="night, first light..."
            className={box}
          />
          <span className="mt-0.5 block text-[10px] normal-case text-zinc-500">
            Reaches the prompt.
          </span>
        </label>
        <label className="block text-[10px] uppercase text-zinc-500">
          Planned duration (sec)
          <input
            aria-label="Scene planned duration in seconds"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            className={box}
          />
        </label>
      </div>

      <label className="block text-[10px] uppercase text-zinc-500">
        Summary
        <textarea
          aria-label="Scene summary"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={2}
          placeholder="What happens here, in a sentence."
          className={box}
        />
        <span className="mt-0.5 block text-[10px] normal-case text-zinc-500">
          Reaches the prompt.
        </span>
      </label>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="block text-[10px] uppercase text-zinc-500">
          Purpose
          <input
            aria-label="Scene purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            placeholder="what this scene is for"
            className={box}
          />
        </label>
        <label className="block text-[10px] uppercase text-zinc-500">
          Emotional beat
          <input
            aria-label="Scene emotional beat"
            value={beat}
            onChange={(e) => setBeat(e.target.value)}
            placeholder="unease, relief..."
            className={box}
          />
        </label>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="block text-[10px] uppercase text-zinc-500">
          Location
          <select
            aria-label="Scene location"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            className={box}
          >
            <option value="">Not set</option>
            {locationsQ.data?.map((location) => (
              <option key={location.id} value={location.id}>{location.name}</option>
            ))}
          </select>
        </label>
        <fieldset className="text-[10px] uppercase text-zinc-500">
          <legend>In this scene</legend>
          <div className="flex flex-wrap gap-2 pt-1">
            {charactersQ.data?.length === 0 && (
              <span className="text-[11px] normal-case text-zinc-500">
                No characters written yet.
              </span>
            )}
            {charactersQ.data?.map((character) => (
              <label
                key={character.id}
                className="flex items-center gap-1 text-[11px] normal-case text-zinc-300"
              >
                <input
                  type="checkbox"
                  aria-label={`${character.name} is in this scene`}
                  checked={characterIds.includes(character.id)}
                  onChange={(e) =>
                    setCharacterIds(
                      e.target.checked
                        ? [...characterIds, character.id]
                        : characterIds.filter((id) => id !== character.id),
                    )
                  }
                />
                {character.name}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="flex justify-end gap-1">
        <button
          type="button"
          onClick={onDone}
          className="rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="flex items-center gap-1 rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {save.isPending ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
          Save scene
        </button>
      </div>
      {save.isError && (
        <p role="alert" className="text-xs text-red-300">
          {toAIError(save.error).detail}
        </p>
      )}
    </div>
  );
}
