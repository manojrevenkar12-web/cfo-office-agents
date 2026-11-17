import { useQuery } from "@tanstack/react-query";
import { api, type ReviewItem } from "../../shared/api";
import { deDate, eur, KIND } from "../../shared/format";
import { COLOUR, LAYOUT } from "../../shared/theme";

function Trace({ subject }: { subject: string }) {
  const q = useQuery({ queryKey: ["trace", subject], queryFn: () => api.traces(subject) });
  if (q.isPending) return <div className="skeleton" />;
  if (q.isError || !q.data.spans.length) return <p className="small muted">No trace for this payment.</p>;
  const spans = q.data.spans.filter((s) => s.name !== "cash.decide");
  const total = Math.max(...spans.map((s) => s.ms), 1);
  return (
    <div aria-label="What the agent did" style={{ marginTop: LAYOUT.radius * 4 }}>
      <h3>What the agent did</h3>
      {spans.map((s) => (
        <div key={s.span} className="small" style={{ display: "grid", gridTemplateColumns: "1fr 120px 60px", gap: 8, alignItems: "center" }}>
          <span>{s.name.replace(/^mcp\./, "")}</span>
          <div className="bar"><i style={{ width: `${(100 * s.ms) / total}%`, background: COLOUR.muted }} /></div>
          <span className="muted" style={{ textAlign: "right" }}>{s.ms.toFixed(1)} ms</span>
        </div>
      ))}
    </div>
  );
}

export function ReviewDetail({ item, busy, onAccept, onReject }: { item: ReviewItem; busy: boolean; onAccept: () => void; onReject: () => void }) {
  const total = item.proposal.reduce((a, l) => a + l.amount_cents, 0);
  return (
    <article className="panel" aria-labelledby="detail">
      <h2 id="detail">{eur(item.amount_cents)} on {deDate(item.day)}</h2>
      <p><span className="tag review">needs a person</span> {item.reason}</p>
      <ul className="evidence small">{item.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
      {item.proposal.length ? (
        <table aria-label="Proposed postings">
          <thead><tr><th>Item</th><th>Posting</th><th className="num">Amount</th></tr></thead>
          <tbody>
            {item.proposal.map((l, i) => (
              <tr key={i}><td>{l.doc ?? "unapplied cash"}</td><td>{KIND[l.kind] ?? l.kind}</td><td className="num">{eur(l.amount_cents)}</td></tr>
            ))}
            <tr><td /><td className="muted">Total</td><td className="num"><b>{eur(total)}</b></td></tr>
          </tbody>
        </table>
      ) : <p className="muted">No proposal: the agent could not explain every cent. Find the items in the ERP.</p>}
      <div className="actions">
        <button className="btn primary" onClick={onAccept} disabled={busy || !item.proposal.length}>{busy ? "Posting…" : "Post proposal"}</button>
        <button className="btn quiet" onClick={onReject} disabled={busy}>Handle in the ERP</button>
      </div>
      <Trace subject={item.subject} />
    </article>
  );
}
