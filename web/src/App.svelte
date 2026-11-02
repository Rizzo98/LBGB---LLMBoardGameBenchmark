<script lang="ts">
  import { onMount } from "svelte";
  import { ApiFailure, fetchLog, fetchLogs } from "./lib/api";
  import { verificationLabel } from "./lib/status";
  import type { LogDetail, LogEntry } from "./lib/types";

  let logs = $state<LogEntry[]>([]);
  let selected = $state<LogDetail | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);

  onMount(() => {
    void load();
  });

  async function load(): Promise<void> {
    loading = true;
    try {
      const response = await fetchLogs();
      logs = response.logs;
      error = null;
    } catch (failure) {
      error = describe(failure);
    } finally {
      loading = false;
    }
  }

  async function open(entry: LogEntry): Promise<void> {
    try {
      selected = await fetchLog(entry.log);
      error = null;
    } catch (failure) {
      error = describe(failure);
    }
  }

  function describe(failure: unknown): string {
    if (failure instanceof ApiFailure || failure instanceof Error) {
      return failure.message;
    }
    return "the console request failed";
  }
</script>

<main>
  <header>
    <h1>LBGB console</h1>
    <p class="subtitle">Read-only records. The record is the evidence.</p>
  </header>

  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  <section aria-label="Records">
    <h2>Records</h2>
    {#if loading}
      <p>Loading records…</p>
    {:else if logs.length === 0}
      <p class="empty">No records under the declared roots.</p>
    {:else}
      <ul class="records">
        {#each logs as entry (entry.log)}
          <li>
            <button
              type="button"
              aria-pressed={selected?.log === entry.log}
              onclick={() => void open(entry)}
            >
              <span class="name">{entry.log}</span>
              <span class="meta">
                {entry.game ?? "unreadable"}{entry.rules_version ? ` · ${entry.rules_version}` : ""}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if selected}
    <section class="detail" aria-label="Selected record">
      <h2>{selected.log}</h2>
      <p class:verified={selected.verified} class:failed={!selected.verified} role="status">
        {verificationLabel(selected)}
      </p>
      <dl>
        <dt>game</dt>
        <dd>{selected.game ?? "unknown"}</dd>
        <dt>rules</dt>
        <dd>{selected.rules_version ?? "unknown"}</dd>
        <dt>schema</dt>
        <dd>{selected.schema_version ?? "unknown"}</dd>
        <dt>engine</dt>
        <dd>{selected.engine_version ?? "unknown"}</dd>
        <dt>terminal</dt>
        <dd>
          {selected.completed === null
            ? "not reconstructed"
            : selected.completed
              ? "completed"
              : "incomplete or abandoned"}
        </dd>
      </dl>
      {#if selected.failure}
        <p class="failure">{selected.failure.kind}: {selected.failure.detail}</p>
      {/if}
    </section>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    background: #f6f5f2;
    color: #1d1d1b;
    font-family:
      ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }

  main {
    max-width: 60rem;
    margin: 0 auto;
    padding: 3rem 1.5rem 5rem;
  }

  header h1 {
    margin: 0;
    font-size: 1.9rem;
    letter-spacing: -0.02em;
  }

  .subtitle {
    margin: 0.4rem 0 2rem;
    color: #5c5a55;
  }

  h2 {
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #5c5a55;
  }

  .records {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.5rem;
  }

  .records button {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
    padding: 0.8rem 1rem;
    border: 1px solid #d8d5cd;
    border-radius: 0.5rem;
    background: #fff;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .records button:hover {
    border-color: #8a857a;
  }

  .records button[aria-pressed="true"] {
    border-color: #1d1d1b;
    box-shadow: inset 0 0 0 1px #1d1d1b;
  }

  .name {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-weight: 600;
  }

  .meta {
    color: #5c5a55;
    font-size: 0.9rem;
  }

  .detail {
    margin-top: 2.5rem;
    padding: 1.25rem 1.5rem;
    border: 1px solid #d8d5cd;
    border-radius: 0.5rem;
    background: #fff;
  }

  .detail h2 {
    margin-top: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-transform: none;
    letter-spacing: 0;
    font-size: 1.2rem;
    color: #1d1d1b;
  }

  .verified {
    font-weight: 600;
    color: #1f5c33;
  }

  .failed {
    font-weight: 600;
    color: #8a2b1d;
  }

  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.35rem 1rem;
    margin: 1rem 0 0;
  }

  dt {
    color: #5c5a55;
  }

  dd {
    margin: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  .failure {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #e6e3da;
    color: #8a2b1d;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9rem;
  }

  .empty {
    color: #5c5a55;
  }

  .error {
    padding: 0.75rem 1rem;
    border-left: 3px solid #8a2b1d;
    background: #fbeceb;
    color: #8a2b1d;
  }
</style>
