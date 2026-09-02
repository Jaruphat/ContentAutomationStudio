import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { initTheme } from "./theme";

// index.html sets the theme class before the first paint; this only re-asserts
// it for entry points that load main.tsx without that inline bootstrap.
initTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
