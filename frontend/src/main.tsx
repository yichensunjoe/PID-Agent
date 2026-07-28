import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { InputDialogHost } from "./editor/InputDialogHost";
import { GridVisualCompatibility } from "./GridVisualCompatibility";
import { ProcessInteractionEnhancements } from "./ProcessInteractionEnhancements";
import { RuntimeEnhancements } from "./RuntimeEnhancements";
import { UiCompatibilityEnhancements } from "./UiCompatibilityEnhancements";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <InputDialogHost />
    <RuntimeEnhancements />
    <ProcessInteractionEnhancements />
    <GridVisualCompatibility />
    <UiCompatibilityEnhancements />
  </StrictMode>,
);
