import { describe, expect, it } from "vitest";
import type { LogDetail } from "../lib/types";
import fixture from "./log.json";

/** The compiler checks the fixture against the client's type; the test checks its meaning. */
const detail: LogDetail = fixture;

describe("the console API contract", () => {
  it("is a verified Catan record", () => {
    expect(detail.schema).toBe("lgbg.console.v1");
    expect(detail.game).toBe("catan");
    expect(detail.rules_version).toBe("catan-rules-6");
    expect(detail.verified).toBe(true);
    expect(detail.actions).toBe(743);
  });
});
