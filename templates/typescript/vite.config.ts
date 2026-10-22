import { sentryVitePlugin } from "@sentry/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react(),
    sentryVitePlugin({
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disable: !process.env.SENTRY_AUTH_TOKEN,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
    }),
  ],
  build: {
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "json-summary", "lcov"],
      reportsDirectory: "coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/instrument.ts", "src/vite-env.d.ts", "src/**/*.test.tsx"],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 70,
        statements: 80,
      },
    },
  },
});
