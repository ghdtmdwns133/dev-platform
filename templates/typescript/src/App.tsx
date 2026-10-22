import { useState } from "react";
import { ErrorPanel } from "./components/ErrorPanel";

export function App() {
  const [error, setError] = useState<string | null>(null);

  return (
    <main>
      <h1>Stage pipeline</h1>
      <p>Critical path totals for a stage dependency graph.</p>
      <button type="button" onClick={() => setError("Synthetic failure for the error panel")}>
        Trigger failure
      </button>
      <ErrorPanel message={error} />
    </main>
  );
}
