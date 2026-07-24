import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { RuntimeEnhancements } from "./RuntimeEnhancements";
import { UiCompatibilityEnhancements } from "./UiCompatibilityEnhancements";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <RuntimeEnhancements />
    <UiCompatibilityEnhancements />
  </StrictMode>,
);
