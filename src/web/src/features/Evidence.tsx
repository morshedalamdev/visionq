import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AgentFixture } from "../api/types";
import { Badge, ErrorState, LoadingState } from "../components/AsyncState";

export function Evidence() {
  const [fixture, setFixture] = useState<AgentFixture | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.agentFixture().then(setFixture).catch(setError);
  }, []);

  return (
    <section>
      <header className="page-header"><div><span className="eyebrow">M5 integration contract</span><h1>Agent evidence</h1><p>This page is presentation structure only. It does not call Qwen, plan tools or verify live answers.</p></div></header>
      <div className="panel question-box">
        <label>Question<textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask an evidence-scoped question…" /></label>
        <button disabled title="Live agent orchestration is planned for M5.T1">Live agent unavailable</button>
      </div>
      {error ? <ErrorState error={error} /> : null}
      {!fixture && !error ? <LoadingState /> : null}
      {fixture ? (
        <div className="evidence-layout">
          <article className="panel answer-panel">
            <div className="panel-heading"><div><Badge value={fixture.evidence_kind} /><h2>{fixture.question}</h2></div><Badge value={fixture.status} /></div>
            <p>{fixture.answer}</p>
            <small>{fixture.verification_status}</small>
            <h3>Numeric claims</h3>
            {fixture.numeric_claims.map((claim, index) => <pre key={index}>{JSON.stringify(claim, null, 2)}</pre>)}
            <h3>Document citations</h3>
            {fixture.citations.map((citation, index) => <pre key={index}>{JSON.stringify(citation, null, 2)}</pre>)}
          </article>
          <aside className="panel trace-panel">
            <h2>Tool trace</h2>
            {fixture.tool_trace.map((trace, index) => <pre key={index}>{JSON.stringify(trace, null, 2)}</pre>)}
            <h2>Answer history</h2>
            <p>Persistent answer history begins with M5.T1. This M4 fixture is not stored as a live answer.</p>
          </aside>
        </div>
      ) : null}
    </section>
  );
}
