/* ──────────────────────────────────────────────────────────────────────────
   StatusBadge -- coloured pill for every entity status in the system.
   Uses the CSS utility classes defined in index.css (.status-*).
   ────────────────────────────────────────────────────────────────────────── */

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const statusKey = (s: string) => s.toLowerCase().replace(/\s+/g, "");

export default function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const key = statusKey(status);

  return (
    <span
      className={`status-${key} inline-block rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide whitespace-nowrap ${className}`}
    >
      {status}
    </span>
  );
}
