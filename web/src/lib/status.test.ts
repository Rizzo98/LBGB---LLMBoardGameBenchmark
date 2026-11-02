import { describe, expect, it } from "vitest";
import { verificationLabel } from "./status";
import type { LogDetail } from "./types";

const base: LogDetail = {
  schema: "lgbg.console.v1",
  log: "full_game",
  game: "catan",
  rules_version: "catan-rules-6",
  schema_version: "catan-actions-1",
  engine_version: "0.1.0",
  actions: 743,
  rejections: 0,
  verified: true,
  completed: true,
  terminal_hash: "abc",
  failure: null,
};

describe("verificationLabel", () => {
  it("names the action count of a verified record", () => {
    expect(verificationLabel(base)).toBe("verified · 743 actions");
  });

  it("says action, not actions, for one", () => {
    expect(verificationLabel({ ...base, actions: 1 })).toBe("verified · 1 action");
  });

  it("localises a failure to its sequence", () => {
    expect(
      verificationLabel({
        ...base,
        verified: false,
        failure: { kind: "hash_mismatch", seq: 219, detail: "expected x" },
      }),
    ).toBe("not verified · hash_mismatch at seq 219");
  });

  it("does not invent a sequence when the record has none", () => {
    expect(
      verificationLabel({
        ...base,
        verified: false,
        failure: { kind: "truncated", seq: null, detail: "cut short" },
      }),
    ).toBe("not verified · truncated");
  });
});
