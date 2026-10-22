import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// The base styles first, so the CSS of pages and components (imported through App) comes later and can adjust them.
import "./styles/blue-tokens.css";
import "./styles/components/blue-components.css";
import "./styles/global.css";
// The texts in the saved language (or Indonesian), ready before anything renders.
import "./app/i18n";
import App from "./app/App";
import { BlueToastProvider } from "./components/blue/Toast";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BlueToastProvider>
      <App />
    </BlueToastProvider>
  </StrictMode>,
);
