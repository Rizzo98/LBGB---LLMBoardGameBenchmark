/** The API shapes the shell consumes (PRD-v3 FR-9.7).
 *
 * `contract/log.json` is checked against `LogDetail` by the compiler, and against the server's
 * actual payload by a Python test. A server change that breaks this file fails one of the two.
 */

export interface LogEntry {
  log: string;
  game: string | null;
  rules_version: string | null;
  problem: string | null;
}

export interface LogList {
  schema: string;
  logs: LogEntry[];
}

export interface Failure {
  kind: string;
  seq: number | null;
  detail: string;
}

export interface LogDetail {
  schema: string;
  log: string;
  game: string | null;
  rules_version: string | null;
  schema_version: string | null;
  engine_version: string | null;
  actions: number | null;
  rejections: number | null;
  verified: boolean;
  completed: boolean | null;
  terminal_hash: string | null;
  failure: Failure | null;
}
