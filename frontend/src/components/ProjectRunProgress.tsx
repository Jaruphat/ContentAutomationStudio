import { useQuery } from "@tanstack/react-query";
import api from "../api/client";
import { useAppState } from "../store/useProjectStore";
import RunProgressBar from "./RunProgressBar";

/**
 * The run progress line, wired to whichever project is selected.
 *
 * Kept apart from `RunProgressBar` so the bar itself takes only data and can
 * be rendered in a test without a store or a network layer.
 */
export default function ProjectRunProgress() {
  const { currentProjectId: projectId } = useAppState();

  // Shots are fetched only to turn ids into labels; a uuid in a status line
  // tells nobody which shot is holding up the queue.
  const { data: scenes } = useQuery({
    queryKey: ["scenes", projectId],
    queryFn: () => api.scenes.list(projectId as string),
    enabled: Boolean(projectId),
  });

  const labels: Record<string, string> = {};
  for (const scene of scenes ?? []) {
    for (const shot of scene.shots ?? []) {
      labels[shot.id] = `Scene ${scene.order} · Shot ${shot.order}`;
    }
  }

  if (!projectId) return null;
  return <RunProgressBar projectId={projectId} shotLabels={labels} />;
}
