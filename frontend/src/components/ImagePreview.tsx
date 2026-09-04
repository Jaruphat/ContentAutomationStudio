import { useEffect, useState } from "react";
import { Maximize2 } from "lucide-react";

/**
 * A thumbnail that shows the whole picture, and opens it full size on click.
 *
 * `object-cover` fills the box by cropping, which is right for a landscape
 * still in a landscape frame and wrong for a character sheet: a standing
 * figure in a short box loses its head, and the head is the part anybody is
 * actually checking. `object-contain` letterboxes instead, so what is on
 * screen is what was generated.
 *
 * A thumbnail still cannot settle whether two views are the same person, so
 * clicking opens the full image over the page.
 */
export default function ImagePreview({
  src,
  alt,
  className = "h-40 w-full",
  caption = "",
}: {
  src: string;
  alt: string;
  /** Box the thumbnail sits in. The image is fitted inside it, never cropped. */
  className?: string;
  /** Shown under the enlarged image, for provenance the gallery already has. */
  caption?: string;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        aria-label={`Enlarge ${alt}`}
        onClick={() => setOpen(true)}
        className={`group relative block overflow-hidden rounded bg-zinc-900 ${className}`}
      >
        <img src={src} alt={alt} className="h-full w-full object-contain" />
        <span
          aria-hidden="true"
          className="absolute right-1 top-1 rounded bg-zinc-950/70 p-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
        >
          <Maximize2 size={12} />
        </span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={alt}
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/80 p-6"
        >
          <img
            src={src}
            alt={alt}
            className="max-h-[85vh] max-w-[90vw] rounded object-contain"
          />
          <p className="text-xs text-zinc-300">
            {caption || alt}
            <span className="ml-2 text-zinc-400">— click anywhere or press Escape to close</span>
          </p>
        </div>
      )}
    </>
  );
}
