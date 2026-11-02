import type { LogDetail } from "./types";

/** The one sentence the badge says about a record. Pure, so it is tested without a browser. */
export function verificationLabel(detail: LogDetail): string {
  if (detail.verified) {
    const actions = detail.actions ?? 0;
    return `verified · ${actions} action${actions === 1 ? "" : "s"}`;
  }
  if (detail.failure === null) {
    return "not verified";
  }
  if (detail.failure.seq === null) {
    return `not verified · ${detail.failure.kind}`;
  }
  return `not verified · ${detail.failure.kind} at seq ${detail.failure.seq}`;
}
