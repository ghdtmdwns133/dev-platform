import http from "node:http";
import process from "node:process";
import * as Sentry from "@sentry/node";

const PORT = 8969;
const live = process.argv.includes("--live");

function fail(message) {
  console.error(message);
  process.exit(1);
}

async function runMock() {
  let received = 0;
  const server = http.createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      received += 1;
      response.writeHead(200, { "content-type": "application/json" });
      response.end("{}");
    });
  });
  await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));
  Sentry.init({
    dsn: `http://public@127.0.0.1:${PORT}/1`,
    environment: "verification",
    tracesSampleRate: 0,
  });
  Sentry.captureException(new Error("dev-platform sentry verification"));
  await Sentry.flush(5000);
  await new Promise((resolve) => server.close(resolve));
  if (received === 0) {
    fail("no envelope received by the mock server");
  }
  console.log(`envelope received (${received})`);
}

async function runLive() {
  const dsn = process.env.SENTRY_DSN;
  const token = process.env.SENTRY_AUTH_TOKEN;
  const org = process.env.SENTRY_ORG;
  const project = process.env.SENTRY_PROJECT;
  if (!dsn || !token || !org || !project) {
    console.error(
      "SENTRY_DSN, SENTRY_AUTH_TOKEN, SENTRY_ORG and SENTRY_PROJECT are required for --live",
    );
    process.exit(2);
  }
  Sentry.init({
    dsn,
    environment: "verification",
    release: process.env.VITE_SENTRY_RELEASE ?? "verify-sentry",
    tracesSampleRate: 0,
  });
  const eventId = Sentry.captureException(
    new Error(`dev-platform sentry verification ${new Date().toISOString()}`),
  );
  const flushed = await Sentry.flush(10000);
  if (!flushed) {
    fail("Sentry flush timed out");
  }
  const response = await fetch(
    `https://sentry.io/api/0/projects/${org}/${project}/events/${eventId}/`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (response.status !== 200) {
    fail(`Sentry event lookup failed with status ${response.status}`);
  }
  console.log(`event id ${eventId}`);
}

try {
  if (live) {
    await runLive();
  } else {
    await runMock();
  }
} finally {
  await Sentry.close();
}
