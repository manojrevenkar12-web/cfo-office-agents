import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { api } from "../../shared/api";
import { deDate } from "../../shared/format";
import { Empty, Failed, Loading } from "../../shared/states";
import { MOTION } from "../../shared/theme";

const OUTCOME: Record<string, [string, string]> = {
  "promise recorded": ["Promise recorded, dunning paused", "posted"],
  "invoice copy drafted": ["Invoice copy drafted", "posted"],
  "payment found in the bank; apply it": ["Payment found in the bank", "review"],
};

function Draft({ name }: { name: string }) {
  const q = useQuery({ queryKey: ["draft", name], queryFn: () => api.draft(name) });
  if (q.isPending) return <div className="skeleton" />;
  if (q.isError) return <p className="small muted">This draft could not be loaded.</p>;
  return <pre className="draft small">{q.data.text}</pre>;
}

export function Collections() {
  const q = useQuery({ queryKey: ["collections"], queryFn: api.collections });
  const [open, setOpen] = useState<string | null>(null);
  if (q.isPending) return <Loading label="Loading replies to dunning letters…" />;
  if (q.isError) return <Failed what="Collections" error={q.error} retry={() => q.refetch()} />;
  const { replies, drafts } = q.data;
  if (!replies.length) return <Empty title="No replies yet">Replies to dunning letters appear here once customers answer.</Empty>;
  return (
    <section aria-labelledby="co">
      <h1 id="co">{replies.length} replies to dunning letters, {drafts.length} answers drafted</h1>
      <p className="muted">The model read each reply; code decided what to do. Every answer is a draft for a person to send.</p>
      <table aria-label="Replies">
        <thead><tr><th>Received</th><th>Customer</th><th>What the agent did</th><th /></tr></thead>
        <tbody>
          {replies.map((r) => {
            const [text, tone] = OUTCOME[r.reason] ?? [r.reason, r.action === "review" ? "review" : "posted"];
            const draft = drafts.find((d) => d.in_reply_to === r.subject)?.name;
            return (
              <tr key={r.subject}>
                <td>{deDate(r.day)}</td><td>{r.kunnr}</td>
                <td><span className={`tag ${tone}`}>{tone === "review" ? "person" : "done"}</span> {text}</td>
                <td>{draft && <button className="btn quiet small" aria-expanded={open === draft} onClick={() => setOpen(open === draft ? null : draft)}>Draft</button>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            transition={{ duration: MOTION.base, ease: MOTION.ease }} style={{ overflow: "hidden", marginTop: 16 }}>
            <Draft name={open} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
