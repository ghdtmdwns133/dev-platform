import * as Sentry from "@sentry/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./instrument";

const container = document.getElementById("root");

if (container) {
  createRoot(container, {
    onCaughtError: Sentry.reactErrorHandler(),
    onRecoverableError: Sentry.reactErrorHandler(),
    onUncaughtError: Sentry.reactErrorHandler(),
  }).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
