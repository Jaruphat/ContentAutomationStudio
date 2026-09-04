import { useEffect, useState } from "react";

/**
 * Whether a panel is folded, remembered per section across sessions.
 *
 * The panels somebody works in are the same ones every session, so the choice
 * is worth keeping. It is only a convenience, though: every read and write is
 * guarded, because private windows and blocked site data throw on access, and
 * losing a fold state is not worth failing a page render over.
 */
export function useSectionFold(id: string, defaultOpen: boolean) {
  const key = `cas.section.${id}`;
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored === null ? defaultOpen : stored === "open";
    } catch {
      return defaultOpen;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, open ? "open" : "closed");
    } catch {
      /* not remembered; not worth reporting */
    }
  }, [key, open]);

  return [open, setOpen] as const;
}
