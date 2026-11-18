import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { loadPlotly } from "./ui/Plot";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// The charting library is large: fetch it while the user logs in or reads the
// scenario, so the preference charts draw instantly when a negotiation starts.
loadPlotly().catch(() => undefined);
