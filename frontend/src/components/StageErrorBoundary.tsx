/* ──────────────────────────────────────────────────────────────────────────
   StageErrorBoundary -- the release gate around one routed stage.

   A crash in a stage component (Story/Storyboard/Generate/Review/Timeline/
   Export) must never blank the whole app: the top bar, stage rail and
   project switcher live outside this boundary in AppLayout, so this only
   ever replaces the <Outlet/> content with a plain-language recovery card.

   The boundary never touches useProjectStore -- Back to Projects navigates,
   Reload data resets only the React Query keys this stage owns, and Retry
   just remounts. None of that clears the user's selected scene/shot/take or
   any other unsaved UI state living in the app store.
   ────────────────────────────────────────────────────────────────────────── */

import { Component, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { AlertTriangle, Copy, Check } from "lucide-react";
import { buildDiagnosticId, sanitizeErrorDetail } from "../lib/errorDiagnostics";

/**
 * Query key prefixes each stage owns. "Reload data" resets only these, so
 * recovering Review does not throw away an in-flight Generate poll or force
 * a refetch of stages the user never touched.
 */
const STAGE_QUERY_PREFIXES: Record<string, string[]> = {
  "/story": ["project", "projects", "characters", "locations", "styles"],
  "/storyboard": ["scenes", "shots", "references", "media-providers"],
  "/generate": [
    "selected-project",
    "workflows",
    "workflow-analysis",
    "jobs",
    "media-providers",
    "media-health",
    "preflight",
    "generation-estimate",
    "queue-status",
    "generation-run-current",
    "generation-runs",
  ],
  "/review": ["takes", "jobs", "regenerate-estimate", "generation-run", "media-providers"],
  "/timeline": ["timeline"],
  "/export": ["timeline"],
};

const STAGE_LABELS: Record<string, string> = {
  "/story": "Story",
  "/storyboard": "Storyboard",
  "/generate": "Generate",
  "/review": "Review",
  "/timeline": "Timeline",
  "/export": "Export",
};

function matchStagePath(pathname: string): string | null {
  return Object.keys(STAGE_LABELS).find((path) => pathname.startsWith(path)) ?? null;
}

function stageLabelFor(pathname: string): string {
  const path = matchStagePath(pathname);
  return path ? STAGE_LABELS[path] : "This stage";
}

function stageQueryPrefixesFor(pathname: string): string[] {
  const path = matchStagePath(pathname);
  return path ? STAGE_QUERY_PREFIXES[path] : [];
}

function resetStageQueries(queryClient: QueryClient, pathname: string): void {
  const prefixes = stageQueryPrefixesFor(pathname);
  queryClient.resetQueries({
    predicate: (query) => {
      const key = query.queryKey[0];
      return typeof key === "string" && prefixes.includes(key);
    },
  });
}

// ── Fallback card ────────────────────────────────────────────────────────

function CopyDiagnosticButton({ diagnosticId }: { diagnosticId: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const clipboard = navigator.clipboard;
    if (!clipboard?.writeText) return;
    clipboard
      .writeText(diagnosticId)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        // Clipboard permission denied -- the id is still visible to copy by hand.
      });
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="flex h-9 items-center gap-1.5 rounded-md border border-zinc-700 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied" : "Copy diagnostic ID"}
    </button>
  );
}

function StageErrorFallback({
  stageName,
  diagnosticId,
  sanitized,
  onReloadData,
  onRetry,
  onBackToProjects,
}: {
  stageName: string;
  diagnosticId: string;
  sanitized: { name: string; message: string };
  onReloadData: () => void;
  onRetry: () => void;
  onBackToProjects: () => void;
}) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex h-full flex-col items-center justify-center gap-4 px-6 py-10 text-center"
    >
      <AlertTriangle size={28} className="text-amber-400" aria-hidden="true" />

      <div className="max-w-md space-y-1">
        <h2 className="text-base font-semibold text-zinc-100">
          {stageName} ran into a problem
        </h2>
        <p className="text-sm text-zinc-400">
          Something went wrong while showing this stage. The rest of the app
          and your other unsaved work are unaffected -- try reloading this
          stage&apos;s data, or go back to Projects.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          onClick={onReloadData}
          className="flex h-9 items-center gap-1.5 rounded-md bg-indigo-600 px-3.5 text-xs font-medium text-white hover:bg-indigo-500"
        >
          Reload data
        </button>
        <button
          type="button"
          onClick={onRetry}
          className="flex h-9 items-center gap-1.5 rounded-md border border-zinc-700 px-3.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
        >
          Retry
        </button>
        <button
          type="button"
          onClick={onBackToProjects}
          className="flex h-9 items-center gap-1.5 rounded-md border border-zinc-700 px-3.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
        >
          Back to Projects
        </button>
        <CopyDiagnosticButton diagnosticId={diagnosticId} />
      </div>

      <details className="w-full max-w-md rounded-md border border-zinc-800 bg-zinc-900/60 p-3 text-left text-xs text-zinc-500">
        <summary className="cursor-pointer select-none font-medium text-zinc-400">
          Technical details
        </summary>
        <dl className="mt-2 space-y-1">
          <div>
            <dt className="inline font-medium text-zinc-400">Stage: </dt>
            <dd className="inline">{stageName}</dd>
          </div>
          <div>
            <dt className="inline font-medium text-zinc-400">Diagnostic ID: </dt>
            <dd className="inline font-mono">{diagnosticId}</dd>
          </div>
          <div>
            <dt className="inline font-medium text-zinc-400">Error: </dt>
            <dd className="inline">
              {sanitized.name}: {sanitized.message}
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

// ── Boundary ─────────────────────────────────────────────────────────────

interface BaseProps {
  children: ReactNode;
  pathname: string;
  queryClient: QueryClient;
  onBackToProjects: () => void;
}

interface BaseState {
  error: Error | null;
  diagnosticId: string | null;
  remountKey: number;
}

class StageErrorBoundaryBase extends Component<BaseProps, BaseState> {
  state: BaseState = { error: null, diagnosticId: null, remountKey: 0 };

  static getDerivedStateFromError(error: Error): Partial<BaseState> {
    return { error };
  }

  componentDidCatch(error: Error): void {
    const stageName = stageLabelFor(this.props.pathname);
    const diagnosticId = buildDiagnosticId(stageName, error);
    const sanitized = sanitizeErrorDetail(error);
    this.setState({ diagnosticId });
    // eslint-disable-next-line no-console -- the project's diagnostics sink for now.
    console.error("[StageErrorBoundary]", {
      diagnosticId,
      stage: stageName,
      name: sanitized.name,
      message: sanitized.message,
      timestamp: new Date().toISOString(),
    });
  }

  /** Navigating to a different stage must not leave a stale fallback behind. */
  componentDidUpdate(prevProps: BaseProps): void {
    if (prevProps.pathname !== this.props.pathname && this.state.error) {
      this.setState({ error: null, diagnosticId: null });
    }
  }

  private clearAndRemount = () => {
    this.setState((s) => ({ error: null, diagnosticId: null, remountKey: s.remountKey + 1 }));
  };

  private handleRetry = () => {
    this.clearAndRemount();
  };

  private handleReloadData = () => {
    resetStageQueries(this.props.queryClient, this.props.pathname);
    this.clearAndRemount();
  };

  private handleBackToProjects = () => {
    this.setState({ error: null, diagnosticId: null });
    this.props.onBackToProjects();
  };

  render() {
    const { error, diagnosticId, remountKey } = this.state;
    if (error) {
      return (
        <StageErrorFallback
          stageName={stageLabelFor(this.props.pathname)}
          diagnosticId={diagnosticId ?? "ERR-00000000"}
          sanitized={sanitizeErrorDetail(error)}
          onReloadData={this.handleReloadData}
          onRetry={this.handleRetry}
          onBackToProjects={this.handleBackToProjects}
        />
      );
    }
    return <div key={remountKey}>{this.props.children}</div>;
  }
}

export default function StageErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  return (
    <StageErrorBoundaryBase
      pathname={location.pathname}
      queryClient={queryClient}
      onBackToProjects={() => navigate("/story")}
    >
      {children}
    </StageErrorBoundaryBase>
  );
}
