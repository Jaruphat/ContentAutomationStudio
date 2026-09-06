import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, Trash2 } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../api/client";
import {
  useAppDispatch,
  useAppState,
  type AppState,
} from "../store/useProjectStore";

const NEW_PROJECT_PRESETS: {
  id: AppState["newProjectTemplateId"];
  label: string;
}[] = [
  { id: "blank", label: "Blank" },
  { id: "plot", label: "Start from Plot" },
  { id: "youtube", label: "YouTube" },
  { id: "shorts", label: "Shorts" },
  { id: "story", label: "Story Video" },
];

/** Persistent project context: always shows what edits apply to. */
export default function ProjectSwitcher() {
  const { currentProjectId, creatingProject } = useAppState();
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const projectsQ = useQuery({ queryKey: ["projects"], queryFn: api.projects.list });
  // Abandoned projects otherwise accumulate in this list for ever. Deleting
  // one takes its scenes, shots and takes with it, so it asks first - and asks
  // in place rather than through a dialog nobody reads.
  const [confirming, setConfirming] = useState(false);
  const current = projectsQ.data?.find((project) => project.id === currentProjectId);
  const remove = useMutation({
    mutationFn: () => api.projects.delete(currentProjectId as string),
    onSuccess: () => {
      setConfirming(false);
      // null, not "": the effect below picks the first remaining project, and
      // an empty string would look selected while matching nothing.
      dispatch({ type: "SET_PROJECT", id: null });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  useEffect(() => {
    if (!currentProjectId && !creatingProject && projectsQ.data?.length) {
      dispatch({ type: "SET_PROJECT", id: projectsQ.data[0].id });
    }
  }, [currentProjectId, creatingProject, projectsQ.data, dispatch]);

  const startNew = (template: AppState["newProjectTemplateId"] = "blank") => {
    const selectedProjectId = currentProjectId;
    if (selectedProjectId) {
      void queryClient.cancelQueries({
        queryKey: ["project", selectedProjectId],
        exact: true,
      });
    }
    dispatch({ type: "START_NEW_PROJECT", template });
    if (location.pathname !== "/story") navigate("/story");
  };

  return (
    <div className="flex min-h-12 shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-950/95 px-3">
      <FolderOpen size={15} className="shrink-0 text-indigo-400" />
      <span className="hidden text-xs font-medium text-zinc-400 sm:inline">Project</span>
      <select
        aria-label="Switch project"
        value={currentProjectId ?? ""}
        onChange={(event) => {
          const id = event.target.value;
          if (id) dispatch({ type: "SET_PROJECT", id });
        }}
        className="min-w-0 max-w-sm flex-1 rounded-md px-2 py-1.5 text-sm"
      >
        {creatingProject && <option value="">New project draft</option>}
        {!creatingProject && !currentProjectId && <option value="">No projects</option>}
        {projectsQ.data?.map((project) => (
          <option key={project.id} value={project.id}>
            {project.title}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => startNew("blank")}
        className="flex shrink-0 items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
      >
        <Plus size={14} /> New
      </button>
      {currentProjectId && !creatingProject && (
        confirming ? (
          <span className="flex shrink-0 items-center gap-1.5 text-xs text-zinc-300">
            Delete “{current?.title ?? "this project"}” and everything in it?
            <button
              type="button"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className="rounded-md bg-red-700 px-2 py-1 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
            >
              {remove.isPending ? "Deleting…" : "Delete"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-md px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
            >
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            aria-label="Delete this project"
            onClick={() => setConfirming(true)}
            className="shrink-0 rounded-md p-1.5 text-zinc-500 hover:bg-red-900/40 hover:text-red-400"
          >
            <Trash2 size={14} />
          </button>
        )
      )}
      <select
        aria-label="New project preset"
        value=""
        onChange={(event) => {
          const template = event.target.value as AppState["newProjectTemplateId"];
          if (template) startNew(template);
        }}
        className="w-32 shrink-0 rounded-md px-2 py-1.5 text-sm"
      >
        <option value="" disabled>Preset…</option>
        {NEW_PROJECT_PRESETS.map((preset) => (
          <option key={preset.id} value={preset.id}>{preset.label}</option>
        ))}
      </select>
    </div>
  );
}
