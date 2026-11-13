import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
// Overpass (road-sign lineage) for headings and numbers, bundled with the app (OFL licence).
import "@fontsource/overpass/600.css";
import "@fontsource/overpass/700.css";
import "@fontsource/overpass/800.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
