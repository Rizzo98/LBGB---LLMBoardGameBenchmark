import type { LogDetail, LogList } from "./types";

export class ApiFailure extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiFailure";
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiFailure(errorMessage(payload, response.status), response.status);
  }
  return payload as T;
}

function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null && "message" in error) {
      const message = (error as { message?: unknown }).message;
      if (typeof message === "string") {
        return message;
      }
    }
  }
  return `the console answered ${status}`;
}

export function fetchLogs(): Promise<LogList> {
  return getJson<LogList>("/api/logs");
}

export function fetchLog(log: string): Promise<LogDetail> {
  return getJson<LogDetail>(`/api/logs/${encodeURIComponent(log)}`);
}
