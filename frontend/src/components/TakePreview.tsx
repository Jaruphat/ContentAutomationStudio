/* ──────────────────────────────────────────────────────────────────────────
   TakePreview -- the real generated media for one take.

   A take's file lives at an absolute path on disk that a browser cannot open,
   so the media is streamed from the backend at /api/media/takes/{id}/file.
   The frame is a constant aspect box because a review grid is only scannable
   if every card is the same size, and the media is drawn `object-contain` so
   framing is judged as it was generated rather than cropped to fit.
   ────────────────────────────────────────────────────────────────────────── */

import { useEffect, useState } from "react";
import { AlertTriangle, FileQuestion, Loader2 } from "lucide-react";
import api from "../api/client";
import type { Take } from "../types";

/** Containers a <video> element can be handed. */
const VIDEO_EXTENSIONS = [".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"];

/** Codec and container strings providers report for moving pictures. */
const VIDEO_CODECS = [
  "h264",
  "avc",
  "hevc",
  "h265",
  "vp8",
  "vp9",
  "av1",
  "mpeg4",
  "prores",
  "mp4",
  "webm",
  "mov",
];

function fileExtension(path: string): string {
  const clean = path.split(/[?#]/)[0];
  const dot = clean.lastIndexOf(".");
  const slash = Math.max(clean.lastIndexOf("/"), clean.lastIndexOf("\\"));
  return dot > slash ? clean.slice(dot).toLowerCase() : "";
}

/**
 * Decide which element can actually play this take.
 *
 * The file extension wins because it is the only signal that describes the
 * bytes the browser is handed. `codec` is provider-reported and is sometimes a
 * container name, sometimes empty -- a hosted still has no codec at all -- and
 * `duration_sec` is a *planned* duration on rows written before the media was
 * probed, so either one alone would eventually feed a PNG to a <video>.
 * Extension first, codec second, duration only as a last resort.
 */
export function mediaKind(take: Take): "video" | "image" {
  const ext = fileExtension(take.file_path);
  if (ext) return VIDEO_EXTENSIONS.includes(ext) ? "video" : "image";

  const codec = (take.codec || "").toLowerCase();
  if (codec) return VIDEO_CODECS.some((c) => codec.includes(c)) ? "video" : "image";

  return take.duration_sec > 0 ? "video" : "image";
}

/**
 * True when the deterministic mock provider produced this take.
 *
 * The mock derives its prompt id from the job id with a `mock-` prefix and
 * that id is copied into the take's provenance, so a mock take stays
 * identifiable long after the provider was switched to a real one. Mock output
 * must never be mistaken for a render, so the label travels with the media
 * rather than living on the page around it.
 */
function isMockTake(take: Take): boolean {
  const provenance = take.provenance ?? {};
  if (provenance.mock === true) return true;
  const promptId =
    typeof provenance.prompt_id === "string" ? provenance.prompt_id : "";
  return promptId.startsWith("mock-");
}

type LoadState = "loading" | "ready" | "error";

export default function TakePreview({
  take,
  className = "",
  nativeAspect = false,
}: {
  take: Take;
  className?: string;
  nativeAspect?: boolean;
}) {
  const [state, setState] = useState<LoadState>("loading");

  // A card is reused for a different take when the grid re-renders or a shot
  // is regenerated, so the load state has to follow the take, not the mount.
  useEffect(() => {
    setState("loading");
  }, [take.id]);

  const frame =
    "relative flex aspect-video w-full items-center justify-center " +
    "overflow-hidden rounded-md border border-zinc-800 bg-zinc-800/60 " +
    className;
  const frameStyle = nativeAspect && take.width > 0 && take.height > 0
    ? { aspectRatio: `${take.width} / ${take.height}`, maxHeight: "34rem" }
    : undefined;

  // Nothing was ever written for this take: not an error, just no media.
  if (!take.file_path.trim()) {
    return (
      <div className={frame} style={frameStyle}>
        <div className="flex flex-col items-center gap-1.5 px-4 text-center">
          <FileQuestion size={24} className="text-zinc-500" />
          <p className="text-xs font-medium text-zinc-400">No media recorded</p>
          <p className="text-[11px] text-zinc-500">
            The job for this take produced no file.
          </p>
        </div>
      </div>
    );
  }

  const src = api.review.mediaUrl(take.id);
  const kind = mediaKind(take);
  const mock = isMockTake(take);

  return (
    <div className={frame} style={frameStyle}>
      {state !== "error" &&
        (kind === "video" ? (
          <video
            key={take.id}
            src={src}
            muted
            playsInline
            preload="metadata"
            controls
            onLoadedMetadata={() => setState("ready")}
            onError={() => setState("error")}
            className={`h-full w-full object-contain transition-opacity ${
              state === "ready" ? "opacity-100" : "opacity-0"
            }`}
          />
        ) : (
          <img
            key={take.id}
            src={src}
            alt={`Take ${take.id.slice(0, 8)}`}
            onLoad={() => setState("ready")}
            onError={() => setState("error")}
            className={`h-full w-full object-contain transition-opacity ${
              state === "ready" ? "opacity-100" : "opacity-0"
            }`}
          />
        ))}

      {state === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs text-zinc-400">
          <Loader2 size={14} className="animate-spin" />
          Loading media...
        </div>
      )}

      {state === "error" && (
        <div className="flex flex-col items-center gap-1.5 px-4 text-center">
          <AlertTriangle size={22} className="text-amber-400" />
          <p className="text-xs font-medium text-amber-300">
            Media missing or unreadable
          </p>
          <p className="text-[11px] text-zinc-400">
            The file may have been moved or deleted. Regenerate the shot to
            produce it again.
          </p>
        </div>
      )}

      {mock && state !== "error" && (
        <span className="absolute left-2 top-2 rounded bg-amber-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
          Deterministic mock
        </span>
      )}
    </div>
  );
}
