/* ──────────────────────────────────────────────────────────────────────────
   ExportPage -- Export project data in various formats.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  Package,
  Film,
  Loader2,
  CheckCircle2,
  Clock,
} from "lucide-react";
import api, { toAIError } from "../api/client";
import ActionError from "../components/ActionError";
import AspectOverrideBanner from "../components/AspectOverrideBanner";
import PublishGate from "../components/PublishGate";
import SubtitleSettingsSection, {
  subtitlePresets,
  subtitlePreviewAspect,
} from "../components/SubtitleSettingsSection";
import { useAppState } from "../store/useProjectStore";

export { subtitlePresets, subtitlePreviewAspect };

interface ExportOption {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  format?: string;
  /** The download filename for this export, given the project id. */
  filename: (projectId: string) => string;
}

/**
 * "Timeline Manifest" and "Generation Manifest" both existed as file names on
 * disk before either had a distinct label here, so a downloaded file and its
 * on-screen name always matched by construction: the label is derived from
 * the same word the filename uses, not chosen separately.
 */
export const exportOptions: ExportOption[] = [
  {
    id: "storyboard_json",
    label: "Storyboard (JSON)",
    description: "Full storyboard with scenes, shots, and prompts in JSON format",
    icon: FileJson,
    format: "json",
    filename: (id) => `storyboard_${id.slice(0, 8)}.json`,
  },
  {
    id: "storyboard_csv",
    label: "Storyboard (CSV)",
    description: "Scenes and shots as a flat spreadsheet-compatible CSV",
    icon: FileSpreadsheet,
    format: "csv",
    filename: (id) => `storyboard_${id.slice(0, 8)}.csv`,
  },
  {
    id: "storyboard_md",
    label: "Storyboard (Markdown)",
    description: "Human-readable storyboard document in Markdown format",
    icon: FileText,
    format: "markdown",
    filename: (id) => `storyboard_${id.slice(0, 8)}.md`,
  },
  {
    id: "prompts",
    label: "Compiled Prompts",
    description: "All compiled image and video prompts with layer breakdowns",
    icon: FileJson,
    filename: (id) => `prompts_${id.slice(0, 8)}.json`,
  },
  {
    id: "manifest",
    label: "Generation Manifest",
    description: "Every generation job and take, with provider, cost and provenance",
    icon: FileJson,
    filename: (id) => `generation_manifest_${id.slice(0, 8)}.json`,
  },
  {
    id: "timeline",
    label: "Timeline Manifest",
    description: "The approved cut: in/out points, transitions and take provenance",
    icon: Film,
    filename: (id) => `timeline_manifest_${id.slice(0, 8)}.json`,
  },
  {
    id: "archive",
    label: "Project Archive (JSON)",
    description: "Complete project metadata as one JSON document. No media files.",
    icon: Package,
    filename: (id) => `archive_${id.slice(0, 8)}.json`,
  },
];

// ── Download helper ──────────────────────────────────────────────────────

function downloadBlob(data: Blob | object | string, filename: string) {
  let blob: Blob;
  if (data instanceof Blob) {
    blob = data;
  } else if (typeof data === "object") {
    blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
  } else {
    blob = new Blob([data], { type: "text/plain" });
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

// ── Export card ───────────────────────────────────────────────────────────

function ExportCard({
  opt,
  projectId,
  onExported,
}: {
  opt: ExportOption;
  projectId: string;
  onExported: (id: string) => void;
}) {
  const Icon = opt.icon;

  const exportMut = useMutation({
    mutationFn: async () => {
      let data: unknown;

      const filename = opt.filename(projectId);
      switch (opt.id) {
        case "storyboard_json":
          data = await api.exports.storyboard(projectId, "json");
          downloadBlob(data as object, filename);
          break;
        case "storyboard_csv":
          data = await api.exports.storyboard(projectId, "csv");
          downloadBlob(data as Blob, filename);
          break;
        case "storyboard_md":
          data = await api.exports.storyboard(projectId, "markdown");
          downloadBlob(data as Blob, filename);
          break;
        case "prompts":
          data = await api.exports.prompts(projectId);
          downloadBlob(data as object, filename);
          break;
        case "manifest":
          data = await api.exports.manifest(projectId);
          downloadBlob(data as object, filename);
          break;
        case "timeline":
          data = await api.exports.timeline(projectId);
          downloadBlob(data as object, filename);
          break;
        case "archive":
          // The archive is JSON metadata, not a binary bundle - the client's
          // own comment on this call says so.
          data = await api.exports.archive(projectId);
          downloadBlob(data as object, filename);
          break;
      }
    },
    onSuccess: () => onExported(opt.id),
  });

  return (
    <div>
      <div className="flex items-start gap-4 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <div className="shrink-0 rounded-lg bg-zinc-800 p-2.5">
          <Icon size={20} className="text-zinc-400" />
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-zinc-200">{opt.label}</h3>
          <p className="mt-0.5 text-xs text-zinc-500">{opt.description}</p>
        </div>

        <button
          onClick={() => exportMut.mutate()}
          disabled={exportMut.isPending}
          className="flex shrink-0 items-center gap-1.5 rounded-md bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
        >
          {exportMut.isPending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : exportMut.isSuccess ? (
            <CheckCircle2 size={13} className="text-green-400" />
          ) : (
            <Download size={13} />
          )}
          {exportMut.isPending
            ? "Exporting..."
            : exportMut.isSuccess
              ? "Done"
              : "Export"}
        </button>
      </div>

      {exportMut.isError && (
        <div className="mt-1.5">
          <ActionError label={opt.label} error={exportMut.error} />
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// ExportPage
// ══════════════════════════════════════════════════════════════════════════

export default function ExportPage() {
  const { currentProjectId } = useAppState();
  const [exportTimestamps, setExportTimestamps] = useState<
    Record<string, Date>
  >({});
  const timelineQ = useQuery({
    queryKey: ["timeline", currentProjectId],
    queryFn: () => api.timeline.get(currentProjectId!),
    enabled: !!currentProjectId,
  });

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <Download size={32} className="mb-3 text-zinc-500" />
        <h2 className="text-lg font-semibold text-zinc-300">No Project Selected</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Go to the Story page and create or select a project first.
        </p>
      </div>
    );
  }

  const handleExported = (id: string) => {
    setExportTimestamps((prev) => ({ ...prev, [id]: new Date() }));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Download size={20} className="text-indigo-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Export</h1>
      </div>

      <p className="text-sm text-zinc-500">
        Export your project data in various formats. Each export will download
        the file directly to your browser.
      </p>

      {/* The decision that is made once, before the files leave: does this
          episode go out. Placed above the export cards because a package that
          is not ready makes every download below it premature. */}
      <PublishGate projectId={currentProjectId} />

      {timelineQ.data && (
        <AspectOverrideBanner
          warnings={timelineQ.data.warnings}
          validation={timelineQ.data.delivery_validation}
        />
      )}

      {/* The timeline manifest backs the delivery-spec banner above; a
          refused read (e.g. stale lineage) must say so rather than silently
          show no banner at all, which reads as "nothing to report". */}
      {timelineQ.isError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-800 bg-red-900/25 px-3 py-2 text-sm text-red-300"
        >
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>
            <span className="font-medium">Timeline status unavailable.</span>{" "}
            {toAIError(timelineQ.error).detail}
          </span>
        </div>
      )}

      <SubtitleSettingsSection projectId={currentProjectId} />

      {/* Export options */}
      <div className="space-y-3">
        {exportOptions.map((opt) => (
          <div key={opt.id}>
            <ExportCard
              opt={opt}
              projectId={currentProjectId}
              onExported={handleExported}
            />
            {exportTimestamps[opt.id] && (
              <div className="mt-1 flex items-center gap-1 pl-14 text-[10px] text-zinc-500">
                <Clock size={10} />
                Last exported:{" "}
                {exportTimestamps[opt.id].toLocaleString()}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
