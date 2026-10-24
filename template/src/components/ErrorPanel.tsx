import * as Sentry from "@sentry/react";
import { useEffect } from "react";

interface ErrorPanelProps {
  message: string | null;
}

export function ErrorPanel({ message }: ErrorPanelProps) {
  useEffect(() => {
    if (message) {
      Sentry.captureException(new Error(message));
    }
  }, [message]);

  if (!message) {
    return null;
  }

  return <p role="alert">{message}</p>;
}
