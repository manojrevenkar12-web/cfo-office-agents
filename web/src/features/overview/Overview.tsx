import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, type Report } from "../../shared/api";
import { eur, pct, RUN, deDate } from "../../shared/format";
import { Empty, Failed, Loading } from "../../shared/states";
import { COLOUR, MOTION } from "../../shared/theme";

function Figures({ r }: { r: Report }) {
  const p = r.runs.platform, b = r.business_case;
  const figs = [
    [pct(p.cash.posted_right_share, 1), "of payments posted right with no person involved"],
    [String(p.cash.posted_wrong), "wrong postings by the agents"],
    [`${b.clerk_hours_saved_per_month} h`, "of clerk time saved per month"],
    [String(b.letters_to_paying_customers_avoided), "dunning letters not sent to customers whose money had arrived"],
  ];
  return (
    <div className="figures">
      {figs.map(([n, t], i) => (
        <motion.div key={t} className="figure" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: MOTION.slow, ease: MOTION.ease, delay: i * MOTION.stagger }}>
          <b>{n}</b><span className="muted">{t}</span>
        </motion.div>
      ))}
    </div>
  );
}

function Compare({ r }: { r: Report }) {
  return (
    <table aria-label="Designs on the same month">
      <thead><tr><th>Design</th><th className="num">Posted right</th><th className="num">Posted wrong</th><th className="num">Wrong amount</th>
        <th className="num">Letters to payers</th><th className="num">Clerk hours</th></tr></thead>
      <tbody>
        {Object.entries(r.runs).map(([k, v]) => (
          <tr key={k} className={k === "platform" ? "row-ours" : ""}>
            <td>{RUN[k] ?? k}</td>
            <td className="num">{pct(v.cash.posted_right_share, 1)}</td>
            <td className="num" style={{ color: v.cash.posted_wrong ? COLOUR.fault : undefined }}>{v.cash.posted_wrong}</td>
            <td className="num">{eur(Math.round(v.cash.posted_wrong_eur * 100))}</td>
            <td className="num">{v.collections.letters_to_customers_who_had_paid}</td>
            <td className="num">{((v.cash.clerk_minutes + v.collections.clerk_minutes) / 60).toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Overview() {
  const q = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  if (q.isPending) return <Loading label="Loading the month's results…" rows={8} />;
  if (q.isError) return <Failed what="The results" error={q.error} retry={() => q.refetch()} />;
  const r = q.data.dev;
  if (!r) return <Empty title="No results yet">Run <code>python -m cofa.eval.cli evaluate</code> to measure the agents on a month of the client's payments.</Empty>;
  return (
    <section aria-labelledby="ov">
      <h1 id="ov">A month of incoming payments at {r.company}</h1>
      <p className="muted">{r.planted.payments} payments and {r.planted.advice_mails} payment advices from {deDate(r.period.from)} to {deDate(r.period.to)}, the same for every design.</p>
      <Figures r={r} />
      <h2>Three ways to run accounts receivable</h2>
      <Compare r={r} />
      <p className="small muted" style={{ marginTop: 16 }}>
        Collections reuses the platform: {pct(r.reuse.collections_new_share)} of its code is new. Gate: {r.gate.filter((g) => g.pass).length} of {r.gate.length} lines pass.
        {q.data.heldout ? ` Held-out client: ${q.data.heldout.gate.filter((g) => g.pass).length} of ${q.data.heldout.gate.length}.` : ""}
      </p>
    </section>
  );
}
