import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { toAIError } from "../api/client";
import type { Take } from "../types";

/** A corner, in fractions of the frame. */
type Point = { x: number; y: number };

const CORNER_LABELS = ["top left", "top right", "bottom right", "bottom left"];

/**
 * Draw text onto a generated frame by pointing at where it goes.
 *
 * No model spells, so anything a viewer has to read is composited afterwards.
 * The corners matter more than the position: a page or a label in a generated
 * frame is a plane seen at an angle, so a patch placed at a centre point and
 * an angle still reads as a sticker laid on top. Four corners follow the
 * plane.
 *
 * They were written as eight numbers in a Python file until now, guessed
 * before the frame existed - which is exactly how two composites in a
 * delivered episode ended up describing a plane the paper was not on. Clicking
 * the frame is the whole point: the corners come from the picture rather than
 * from an estimate of it.
 */
export default function CompositeEditor({
  take,
  onDone,
}: {
  take: Take;
  onDone?: (compositedTakeId: string) => void;
}) {
  const [corners, setCorners] = useState<Point[]>([]);
  const [text, setText] = useState("");
  const [colour, setColour] = useState("#141414");
  const [patch, setPatch] = useState("#f2efe6");
  const [usePatch, setUsePatch] = useState(true);
  const qc = useQueryClient();

  const apply = useMutation({
    mutationFn: () => {
      const asPairs = corners.map((point) => [point.x, point.y]);
      const layers = [];
      if (usePatch) {
        // A model does not leave a blank area when asked; it writes a
        // plausible smear. Real text drawn over a fake headline is two
        // headlines, so the patch goes down first.
        layers.push({ type: "rect" as const, colour: patch, corners: asPairs });
      }
      layers.push({
        type: "text" as const,
        text,
        colour,
        size: 0.03,
        corners: asPairs,
      });
      return api.review.composite(take.id, layers);
    },
    onSuccess: (composited) => {
      qc.invalidateQueries({ queryKey: ["takes"] });
      onDone?.(composited.id);
    },
  });

  const place = (event: React.MouseEvent<HTMLImageElement>) => {
    if (corners.length >= 4) return;
    const box = event.currentTarget.getBoundingClientRect();
    setCorners([
      ...corners,
      {
        x: Number(((event.clientX - box.left) / box.width).toFixed(4)),
        y: Number(((event.clientY - box.top) / box.height).toFixed(4)),
      },
    ]);
  };

  const ready = corners.length === 4 && text.trim() !== "";

  return (
    <div className="space-y-2 rounded border border-zinc-700 p-3">
      <p className="text-xs font-medium text-zinc-300">Composite text onto this frame</p>
      <p className="text-[11px] text-zinc-400">
        {corners.length < 4
          ? `Click the ${CORNER_LABELS[corners.length]} corner of the surface the text sits on.`
          : "Four corners set. They follow the plane, so the text lies on the surface rather than over it."}
      </p>
      <div className="relative inline-block">
        <img
          src={api.review.mediaUrl(take.id)}
          alt="Frame to composite onto"
          onClick={place}
          className="max-h-96 cursor-crosshair rounded border border-zinc-700"
        />
        {corners.map((point, index) => (
          <span
            key={index}
            aria-label={`Corner ${index + 1}`}
            style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
            className="pointer-events-none absolute -ml-1.5 -mt-1.5 h-3 w-3 rounded-full border border-black bg-amber-400 text-[8px]"
          />
        ))}
      </div>
      <label className="block text-xs text-zinc-400">
        Text
        <input
          aria-label="Composite text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="DELIVERY 14 MARCH 2027"
          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
        />
      </label>
      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400">
        <label className="flex items-center gap-1">
          Ink
          <input aria-label="Text colour" type="color" value={colour}
                 onChange={(e) => setColour(e.target.value)} className="h-6 w-8" />
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={usePatch}
                 onChange={(e) => setUsePatch(e.target.checked)} />
          Cover what is under it
        </label>
        {usePatch && (
          <label className="flex items-center gap-1">
            Patch
            <input aria-label="Patch colour" type="color" value={patch}
                   onChange={(e) => setPatch(e.target.value)} className="h-6 w-8" />
          </label>
        )}
        <button type="button" onClick={() => setCorners([])}
                className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-300">
          Clear corners
        </button>
      </div>
      <p className="text-[11px] text-zinc-400">
        This makes a new take of the same shot, to be reviewed like any other.
        The frame it is drawn on is not changed.
      </p>
      <button
        type="button"
        disabled={!ready || apply.isPending}
        onClick={() => apply.mutate()}
        className="rounded bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50"
      >
        {apply.isPending ? "Compositing…" : "Composite"}
      </button>
      {apply.isError && (
        <p role="alert" className="text-xs text-red-300">
          {toAIError(apply.error).detail}
        </p>
      )}
    </div>
  );
}
