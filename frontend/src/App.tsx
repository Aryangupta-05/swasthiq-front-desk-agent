import { useCallback, useEffect, useState } from "react";
import type { Detail, Sample, Summary } from "./types";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      body?.detail
        ? JSON.stringify(body.detail)
        : `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}
const labels: Record<string, string> = {
  clinical_urgent: "Clinical · urgent",
  medical_advice: "Medical advice",
  not_authorised: "Not authorised",
  ambiguous_patient: "Ambiguous patient",
  out_of_scope: "Out of scope",
};
function Badge({ value }: { value: string | null }) {
  return (
    <span className={`badge ${value ?? ""}`}>
      {value ? (labels[value] ?? value.replaceAll("_", " ")) : "—"}
    </span>
  );
}
function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export default function App() {
  const [summary, setSummary] = useState<Summary>({
    runs: [],
    counters: { total: 0, completed: 0, escalated: 0, urgent: 0, open: 0 },
  });
  const [samples, setSamples] = useState<Sample[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [view, setView] = useState("queue");
  const [filter, setFilter] = useState("open");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("Loading conversations…");
  const [sampleId, setSampleId] = useState("cv_0011");
  const [composer, setComposer] = useState(false);
  const [script, setScript] = useState("");
  const [today, setToday] = useState("2026-10-01");
  const refresh = useCallback(async () => {
    setSummary(await api<Summary>("/api/runs"));
  }, []);
  useEffect(() => {
    if (!composer) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),select,input,textarea,a[href]",
        ) ?? [],
      );
    focusable()[0]?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") setComposer(false);
      if (event.key !== "Tab") return;
      const elements = focusable();
      const first = elements[0],
        last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, [composer]);
  useEffect(() => {
    let active = true;
    Promise.all([api<Summary>("/api/runs"), api<Sample[]>("/api/samples")])
      .then(([s, cs]) => {
        if (active) {
          setSummary(s);
          setSamples(cs);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setBusy("");
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const sample = samples.find((s) => s.id === sampleId);
    if (sample) {
      setScript(sample.turns.join("\n"));
      setToday(sample.today);
    }
  }, [samples, sampleId]);
  async function open(runId: string) {
    setError("");
    setBusy("Loading transcript…");
    try {
      setDetail(await api<Detail>(`/api/runs/${runId}`));
      setView("detail");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  }
  async function resolve(runId: string) {
    setBusy("Resolving handoff…");
    setError("");
    try {
      await api(`/api/runs/${runId}/resolve`, { method: "POST" });
      await refresh();
      if (detail?.run_id === runId)
        setDetail(await api<Detail>(`/api/runs/${runId}`));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  }
  async function execute(all = false) {
    setBusy("Running conversation…");
    setError("");
    try {
      const cases = all
        ? samples.filter((s) => s.id.startsWith("cv_"))
        : [{ id: sampleId, today, turns: script.split("\n").filter(Boolean) }];
      let last = "";
      for (let i = 0; i < cases.length; i++) {
        const s = cases[i];
        setBusy(`Running ${s.id} (${i + 1}/${cases.length})…`);
        const response = await api<{ run_id: string }>("/api/run", {
          method: "POST",
          body: JSON.stringify({
            conversation_id: s.id,
            today: s.today,
            turns: s.turns,
          }),
        });
        last = response.run_id;
      }
      await refresh();
      setComposer(false);
      if (!all && last) {
        setDetail(await api<Detail>(`/api/runs/${last}`));
        setView("detail");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  }
  const rows = summary.runs.filter(
    (r) =>
      filter === "all" ||
      (filter === "resolved"
        ? r.resolved
        : r.terminal_state === "escalated" && !r.resolved),
  );
  const cards = [
    ["Conversations", summary.counters.total, "Recorded runs"],
    [
      "Completed by agent",
      summary.counters.completed,
      "Booked, moved or cancelled",
    ],
    [
      "Escalated",
      summary.counters.escalated,
      `${summary.counters.open} still open`,
    ],
    ["Urgent", summary.counters.urgent, "Clinical · unresolved"],
  ] as const;
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <a
          className="brand"
          href="#"
          aria-label="Sunrise Clinic home"
          onClick={() => setView("queue")}
        >
          ✚
        </a>
        <span className="nav-divider" />
        <button
          className={view === "queue" ? "nav-icon active" : "nav-icon"}
          onClick={() => setView("queue")}
          aria-label="Handoff queue"
          title="Handoff queue"
        >
          ▦
        </button>
        <button
          className={view === "detail" ? "nav-icon active" : "nav-icon"}
          disabled={!detail}
          onClick={() => setView("detail")}
          aria-label="Conversation detail"
          title="Conversation detail"
        >
          ☷
        </button>
        <button
          className="nav-icon"
          onClick={() => setComposer(true)}
          aria-label="Run a conversation"
          title="Run a conversation"
        >
          ＋
        </button>
        <div className="sidebar-bottom">
          <span className="connection-dot" title="Synthetic clinic data" />
          <span className="avatar" title="Front desk workspace">
            FD
          </span>
        </div>
      </aside>
      <main>
        <div className="workspace-line">
          <span>
            Sunrise Clinic <span className="slash">/</span> Front desk
          </span>
          <span className="synthetic">Synthetic data</span>
        </div>
        <header>
          <div>
            <div className="eyebrow">FRONT DESK WORKSPACE</div>
            <h1>
              {view === "detail" && detail
                ? `Conversation ${detail.result.conversation_id}`
                : "Handoff Queue"}
            </h1>
            <p>
              Sunrise Clinic, Dehradun{" "}
              <span>
                —{" "}
                {view === "detail" && detail
                  ? `${new Date(detail.created_at).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata" })}, ${formatTime(detail.created_at)} IST`
                  : "conversations the agent escalated"}
              </span>
            </p>
          </div>
          <div className="header-actions">
            {view === "detail" && detail ? (
              <Badge
                value={
                  detail.result.escalation_reason ??
                  detail.result.terminal_state
                }
              />
            ) : (
              <span className="open-count">{summary.counters.open} OPEN</span>
            )}
            <button
              className="button secondary"
              onClick={() => setComposer(true)}
              disabled={Boolean(busy)}
            >
              Run conversation
            </button>
          </div>
        </header>
        {error && !composer && (
          <div className="alert" role="alert">
            {error}
            <button
              onClick={() => {
                setError("");
                refresh().catch((e) => setError(String(e)));
              }}
            >
              Retry
            </button>
          </div>
        )}
        {busy && (
          <div className="progress" role="status">
            <span className="spinner" />
            {busy}
          </div>
        )}
        {view === "queue" ? (
          <>
            <section className="counters" aria-label="Conversation counters">
              {cards.map(([name, count, note]) => (
                <article className="counter" key={name}>
                  <div>{name}</div>
                  <strong>{count}</strong>
                  <small
                    className={
                      name === "Urgent"
                        ? "red"
                        : name === "Escalated"
                          ? "blue"
                          : ""
                    }
                  >
                    {note}
                  </small>
                </article>
              ))}
            </section>
            <section className="panel queue-panel">
              <div className="panel-heading">
                <h2>
                  {filter === "open"
                    ? "Open handoffs"
                    : filter === "resolved"
                      ? "Resolved handoffs"
                      : "All conversations"}
                </h2>
                <div className="segmented" aria-label="Conversation filter">
                  {["open", "resolved", "all"].map((f) => (
                    <button
                      key={f}
                      aria-pressed={filter === f}
                      onClick={() => setFilter(f)}
                    >
                      {f === "all" ? "All runs" : f}
                    </button>
                  ))}
                </div>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Conversation</th>
                      <th>Caller said</th>
                      <th>Reason / state</th>
                      <th>Time · IST</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.run_id}>
                        <td>
                          <button
                            className="conversation-link"
                            onClick={() => open(r.run_id)}
                          >
                            {r.conversation_id}
                          </button>
                          <small>
                            {r.resolved
                              ? "Resolved"
                              : r.terminal_state === "escalated"
                                ? "Needs review"
                                : "Completed run"}
                          </small>
                        </td>
                        <td className="excerpt">“{r.excerpt}”</td>
                        <td>
                          <Badge
                            value={r.escalation_reason ?? r.terminal_state}
                          />
                        </td>
                        <td className="time">{formatTime(r.created_at)}</td>
                        <td>
                          {r.terminal_state === "escalated" && !r.resolved ? (
                            <button
                              className="button resolve"
                              disabled={Boolean(busy)}
                              onClick={() => resolve(r.run_id)}
                            >
                              Resolve
                            </button>
                          ) : (
                            <button
                              className="button secondary compact"
                              onClick={() => open(r.run_id)}
                            >
                              View
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!rows.length && (
                <div className="empty">
                  <span className="empty-icon">✓</span>
                  <h3>
                    {summary.counters.total
                      ? "No handoffs in this view"
                      : "Your queue is clear"}
                  </h3>
                  <p>
                    {summary.counters.total
                      ? "Choose All runs to inspect completed conversations."
                      : "Run the supplied conversations to populate this workspace with real results."}
                  </p>
                  <button
                    className="button"
                    onClick={() => execute(true)}
                    disabled={Boolean(busy) || !samples.length}
                  >
                    Run 15 supplied samples
                  </button>
                </div>
              )}
              <div className="panel-footer">
                <span>
                  {rows.length} {filter === "open" ? "open handoffs" : "runs"} ·
                  each row is a real backend execution
                </span>
                <button
                  className="text-button"
                  disabled={Boolean(busy)}
                  onClick={() => execute(true)}
                >
                  Run supplied samples
                </button>
              </div>
            </section>
          </>
        ) : (
          detail && (
            <>
              <button className="back-link" onClick={() => setView("queue")}>
                ← Back to handoff queue
              </button>
              <div className="detail-grid">
                <section className="panel transcript">
                  <div className="panel-heading">
                    <h2>Transcript and tool calls</h2>
                    <span className="subtle">{detail.trace.length} events</span>
                  </div>
                  <div className="preflight-note">
                    Fixed script · all caller turns pass safety preflight before
                    any appointment change.
                  </div>
                  <ol className="timeline">
                    {detail.trace.map((event, index) => (
                      <li
                        key={`${detail.run_id}-${index}`}
                        className={`event ${event.type}`}
                      >
                        <span className="speaker">
                          {event.type === "caller"
                            ? "CALLER"
                            : event.type === "tool"
                              ? "TOOL"
                              : "AGENT"}
                        </span>
                        {event.type === "tool" ? (
                          <div className="tool-card">
                            <code>
                              {event.name}({JSON.stringify(event.arguments)})
                            </code>
                            <details>
                              <summary>Tool result</summary>
                              <pre>{JSON.stringify(event.result, null, 2)}</pre>
                            </details>
                          </div>
                        ) : (
                          <div className="bubble">{event.text}</div>
                        )}
                      </li>
                    ))}
                  </ol>
                  <div
                    className={`grounding-note ${detail.result.terminal_state === "escalated" ? "clinical" : ""}`}
                  >
                    {detail.schedule_unchanged
                      ? "No appointment was created, moved or cancelled."
                      : "Appointment change committed by the tool layer."}
                  </div>
                </section>
                <aside className="panel outcome">
                  <h2>Outcome</h2>
                  <dl>
                    {Object.entries({
                      terminal_state: detail.result.terminal_state,
                      escalation_reason: detail.result.escalation_reason,
                      patient_id: detail.result.patient_id,
                      appointment_id: detail.result.appointment_id,
                      tool_calls: detail.result.tool_calls.length,
                      turns: detail.result.metrics.turns,
                      tokens: detail.result.metrics.tokens,
                      latency_ms: detail.result.metrics.latency_ms,
                    }).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key}</dt>
                        <dd>{value === null ? "null" : value}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="determinism">
                    <h3>DETERMINISM</h3>
                    <p>
                      {detail.determinism.runs} observed run(s),{" "}
                      {detail.determinism.fingerprints.length} fingerprint(s).
                    </p>
                    <span
                      className={`badge ${detail.determinism.stable ? "booked" : ""}`}
                    >
                      {detail.determinism.stable
                        ? "Stable across 3+ runs"
                        : "Needs 3 runs"}
                    </span>
                  </div>
                  <div className="model-info">
                    <h3>EXTRACTION</h3>
                    <p>
                      {detail.model.model ?? "Deterministic policy"}
                      <br />
                      <span>{detail.model.status.replaceAll("_", " ")}</span>
                    </p>
                  </div>
                  {detail.result.terminal_state === "escalated" && (
                    <button
                      className="button full"
                      disabled={detail.resolved || Boolean(busy)}
                      onClick={() => resolve(detail.run_id)}
                    >
                      {detail.resolved ? "Resolved" : "Resolve handoff"}
                    </button>
                  )}
                  <details className="raw">
                    <summary>Machine-readable result</summary>
                    <pre>{JSON.stringify(detail.result, null, 2)}</pre>
                  </details>
                </aside>
              </div>
            </>
          )
        )}
        <footer>
          Grounded in clinic tools. Human review when needed.
          <span>Asia/Kolkata · evaluation snapshots reset per request</span>
        </footer>
      </main>
      {composer && (
        <div className="modal-backdrop">
          <section
            className="composer panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="composer-title"
          >
            <div className="panel-heading">
              <h2 id="composer-title">Run a conversation</h2>
              <button
                className="close"
                onClick={() => setComposer(false)}
                aria-label="Close conversation runner"
              >
                ×
              </button>
            </div>
            {error && (
              <div className="alert" role="alert">
                {error}
              </div>
            )}
            <p className="subtle">
              Edit a fixed script. Each line is one caller turn. Uses the
              original synthetic clinic snapshot.
            </p>
            <label>
              Conversation
              <select
                aria-label="Conversation"
                value={sampleId}
                onChange={(e) => setSampleId(e.target.value)}
              >
                {samples.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id} · {s.description}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reference date
              <input
                type="date"
                value={today}
                onChange={(e) => setToday(e.target.value)}
                required
              />
            </label>
            <label>
              Caller turns
              <textarea
                rows={7}
                value={script}
                onChange={(e) => setScript(e.target.value)}
              />
            </label>
            <div className="composer-actions">
              <button
                className="button secondary"
                onClick={() => setComposer(false)}
              >
                Cancel
              </button>
              <button
                className="button"
                onClick={() => execute()}
                disabled={Boolean(busy) || !script.trim() || !today}
              >
                Execute script
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
