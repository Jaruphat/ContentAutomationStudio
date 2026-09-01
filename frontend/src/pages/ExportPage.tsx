/* ──────────────────────────────────────────────────────────────────────────
   ExportPage -- Export project data in various formats.
   ────────────────────────────────────────────────────────────────────────── */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
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
import api from "../api/client";
import { useAppState } from "../store/useProjectStore";

interface ExportOption {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  format?: string;
}

const exportOptions: ExportOption[] = [
  {
    id: "storyboard_json",
    label: "Storyboard (JSON)",
    description: "Full storyboard with scenes, shots, and prompts in JSON format",
    icon: FileJson,
    format: "json",
  },
  {
    id: "storyboard_csv",
    label: "Storyboard (CSV)",
    description: "Scenes and shots as a flat spreadsheet-compatible CSV",
    icon: FileSpreadsheet,
    format: "csv",
  },
  {
    id: "storyboard_md",
    label: "Storyboard (Markdown)",
    description: "Human-readable storyboard document in Markdown format",
    icon: FileText,
    format: "markdown",
  },
  {
    id: "prompts",
    label: "Compiled Prompts",
    description: "All compiled image and video prompts with layer breakdowns",
    icon: FileJson,
  },
  {
    id: "manifest",
    label: "Timeline Manifest",
    description: "Structured manifest of the approved timeline sequence",
    icon: FileJson,
  },
  {
    id: "timeline",
    label: "Timeline Export",
    description: "Timeline data with in/out points and transition details",
    icon: Film,
  },
  {
    id: "archive",
    label: "Project Archive",
    description: "Complete project archive (ZIP) with all data and metadata",
    icon: Package,
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

      switch (opt.id) {
        case "storyboard_json":
          data = await api.exports.storyboard(projectId, "json");
          downloadBlob(data as object, `storyboard_${projectId.slice(0, 8)}.json`);
          break;
        case "storyboard_csv":
          data = await api.exports.storyboard(projectId, "csv");
          downloadBlob(data as Blob, `storyboard_${projectId.slice(0, 8)}.csv`);
          break;
        case "storyboard_md":
          data = await api.exports.storyboard(projectId, "markdown");
          downloadBlob(data as Blob, `storyboard_${projectId.slice(0, 8)}.md`);
          break;
        case "prompts":
          data = await api.exports.prompts(projectId);
          downloadBlob(data as object, `prompts_${projectId.slice(0, 8)}.json`);
          break;
        case "manifest":
          data = await api.exports.manifest(projectId);
          downloadBlob(data as object, `manifest_${projectId.slice(0, 8)}.json`);
          break;
        case "timeline":
          data = await api.exports.timeline(projectId);
          downloadBlob(data as object, `timeline_${projectId.slice(0, 8)}.json`);
          break;
        case "archive":
          data = await api.exports.archive(projectId);
          downloadBlob(data as Blob, `project_${projectId.slice(0, 8)}_archive.zip`);
          break;
      }
    },
    onSuccess: () => onExported(opt.id),
  });

  return (
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

      {exportMut.isError && (
        <span className="text-xs text-red-400">Failed</span>
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

  if (!currentProjectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center px-8">
        <Download size={32} className="mb-3 text-zinc-600" />
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
