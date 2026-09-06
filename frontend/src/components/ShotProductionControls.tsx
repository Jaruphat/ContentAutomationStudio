import { useQuery } from "@tanstack/react-query";
import api from "../api/client";

/**
 * The three decisions a shot carries that no page could set.
 *
 * They are grouped because they are the same kind of decision - how this shot
 * is produced, rather than what is in it - and because each of them silently
 * decided something in a delivered episode while being reachable only by
 * posting to the API.
 */

export interface ShotProduction {
  workflowPresetId: string;
  includeInCut: boolean;
  negativePrompt: string;
}

export default function ShotProductionControls({
  workflowPresetId,
  includeInCut,
  negativePrompt,
  onChange,
}: ShotProduction & { onChange: (next: Partial<ShotProduction>) => void }) {
  const workflowsQ = useQuery({ queryKey: ["workflows"], queryFn: api.workflows.list });
  const box = "w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100";

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          {/* Left on the project's workflow almost always. Named per shot when
              one shot needs a different graph - a guidance scale that lets the
              prompt move the framing, say - without changing what the others
              generate with. */}
          <label className="text-[10px] uppercase text-zinc-500">Workflow</label>
          <select
            aria-label="Shot workflow"
            value={workflowPresetId}
            onChange={(e) => onChange({ workflowPresetId: e.target.value })}
            className={box}
          >
            <option value="">Project default</option>
            {workflowsQ.data?.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>{workflow.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase text-zinc-500">Negative prompt</label>
          <input
            aria-label="Shot negative prompt"
            value={negativePrompt}
            placeholder="what must not be in this frame"
            onChange={(e) => onChange({ negativePrompt: e.target.value })}
            className={box}
          />
          <span className="mt-0.5 block text-[10px] text-zinc-500">
            Added to the style's own negatives, not instead of them.
          </span>
        </div>
      </div>
      <label className="flex items-start gap-2 text-xs text-zinc-300">
        <input
          type="checkbox"
          aria-label="Include this shot in the cut"
          checked={includeInCut}
          onChange={(e) => onChange({ includeInCut: e.target.checked })}
          className="mt-0.5"
        />
        <span>
          Include in the cut
          <span className="ml-1 text-[10px] text-zinc-500">
            — turn this off for a key image that exists only so a later clip can
            animate from it. Left on, it plays as a still and lengthens the film.
          </span>
        </span>
      </label>
    </div>
  );
}
