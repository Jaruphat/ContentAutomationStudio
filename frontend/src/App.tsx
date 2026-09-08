/* ──────────────────────────────────────────────────────────────────────────
   App -- Root component with routing and providers.
   ────────────────────────────────────────────────────────────────────────── */

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { lazy } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProjectStoreProvider } from "./store/useProjectStore";
import AppLayout from "./components/AppLayout";
import { ThemeProvider } from "./theme";

const CreatePage = lazy(() => import("./pages/CreatePage"));
const ChannelPage = lazy(() => import("./pages/ChannelPage"));
const StoryPage = lazy(() => import("./pages/StoryPage"));
const StoryboardPage = lazy(() => import("./pages/StoryboardPage"));
const GeneratePage = lazy(() => import("./pages/GeneratePage"));
const ReviewPage = lazy(() => import("./pages/ReviewPage"));
const MotionPage = lazy(() => import("./pages/MotionPage"));
const TimelinePage = lazy(() => import("./pages/TimelinePage"));
const ExportPage = lazy(() => import("./pages/ExportPage"));
const WorkflowsPage = lazy(() => import("./pages/WorkflowsPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

export default function App() {
  return (
    <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <ProjectStoreProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/create" element={<CreatePage />} />
              <Route path="/channel" element={<ChannelPage />} />
              <Route path="/story" element={<StoryPage />} />
              <Route path="/storyboard" element={<StoryboardPage />} />
              <Route path="/generate" element={<GeneratePage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/motion" element={<MotionPage />} />
              <Route path="/timeline" element={<TimelinePage />} />
              <Route path="/export" element={<ExportPage />} />
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="*" element={<Navigate to="/create" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ProjectStoreProvider>
    </QueryClientProvider>
    </ThemeProvider>
  );
}
