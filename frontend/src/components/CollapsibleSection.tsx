import { ChevronDown, ChevronRight } from "lucide-react";
import { useSectionFold } from "./useSectionFold";

/**
 * A panel that folds to its heading.
 *
 * The authoring stages stack several tall panels on one page and only one is
 * usually in use, so the rest push the work off screen. Folding keeps them
 * listed - a hidden panel a user cannot find is worse than a long page - and
 * remembers the choice per section, because the panels somebody works in are
 * the same ones every session.
 *
 * Contents are unmounted rather than hidden with CSS: these panels hold live
 * queries and generation forms, and a folded one should not keep polling.
 */
export default function CollapsibleSection({
  id,
  title,
  summary = "",
  defaultOpen = true,
  children,
}: {
  /** Stable key for remembering the fold state. */
  id: string;
  title: string;
  /** A line worth reading while folded, such as how many items are inside. */
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useSectionFold(id, defaultOpen);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <button
        type="button"
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} ${title}`}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        {summary && <span className="ml-auto text-xs text-zinc-500">{summary}</span>}
      </button>
      {open && <div className="border-t border-zinc-800 p-4">{children}</div>}
    </section>
  );
}
