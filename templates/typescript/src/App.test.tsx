import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as Sentry from "@sentry/react";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  afterEach(async () => {
    cleanup();
    await Sentry.close();
  });

  it("renders the stage pipeline heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Stage pipeline" })).toBeInTheDocument();
  });

  it("renders an alert when the failure button is pressed", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Trigger failure" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Synthetic failure");
  });

  it("captures error envelopes through a custom transport", async () => {
    const sent: unknown[] = [];
    Sentry.init({
      dsn: "http://public@127.0.0.1:8969/1",
      defaultIntegrations: false,
      transport: () => ({
        flush: async () => true,
        send: async (envelope) => {
          sent.push(envelope);
          return { statusCode: 200 };
        },
      }),
    });

    Sentry.captureException(new Error("custom transport verification"));
    await Sentry.flush(2000);

    expect(sent.length).toBeGreaterThan(0);
  });
});
