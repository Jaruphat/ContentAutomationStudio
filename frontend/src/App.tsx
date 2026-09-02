/* ──────────────────────────────────────────────────────────────────────────
   App -- Root component with routing and providers.
   ────────────────────────────────────────────────────────────────────────── */

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProjectStoreProvider } from "./store/useProjectStore";
import AppLayout from "./components/AppLayout";
import StoryPage from "./pages/StoryPage";
import StoryboardPage from "./pages/StoryboardPage";
import GeneratePage from "./pages/GeneratePage";
import ReviewPage from "./pages/ReviewPage";
import TimelinePage from "./pages/TimelinePage";
import ExportPage from "./pages/ExportPage";
import { ThemeProvider } from "./theme";

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
              <Route path="/story" element={<StoryPage />} />
              <Route path="/storyboard" element={<StoryboardPage />} />
              <Route path="/generate" element={<GeneratePage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/timeline" element={<TimelinePage />} />
              <Route path="/export" element={<ExportPage />} />
              <Route path="*" element={<Navigate to="/story" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ProjectStoreProvider>
    </QueryClientProvider>
    </ThemeProvider>
  );
}
