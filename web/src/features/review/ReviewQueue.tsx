import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { api } from "../../shared/api";
import { deDate, eur } from "../../shared/format";
import { Empty, Failed, Loading } from "../../shared/states";
import { MOTION } from "../../shared/theme";
import { ReviewDetail } from "./ReviewDetail";

export function ReviewQueue() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["review"], queryFn: api.review });
  const [picked, setPicked] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const done = { onSuccess: () => { setPicked(null); setProblem(null); qc.invalidateQueries({ queryKey: ["review"] }); },
                 onError: (e: Error) => setProblem(e.message) };
  const accept = useMutation({ mutationFn: api.accept, ...done });
  const reject = useMutation({ mutationFn: api.reject, ...done });
  if (q.isPending) return <Loading label="Loading the review queue…" />;
  if (q.isError) return <Failed what="The review queue" error={q.error} retry={() => q.refetch()} />;
  const items = q.data.items;
  if (!items.length) return <Empty title="Nothing to review">Every payment so far was posted or is waiting for its advice.</Empty>;
  const current = items.find((i) => i.subject === picked) ?? items[0];
  return (
    <section aria-labelledby="rq">
      <h1 id="rq">{items.length} payments need a person</h1>
      <p className="muted">Each comes with the reason, the evidence and, where every cent could be explained, a proposal to post.</p>
      <div className="split">
        <ul className="list" aria-label="Payments to review">
          <AnimatePresence initial={false}>
            {items.map((i) => (
              <motion.li key={i.subject} layout exit={{ opacity: 0, x: -16 }} transition={{ duration: MOTION.base, ease: MOTION.ease }}>
                <button aria-current={i.subject === current.subject} onClick={() => setPicked(i.subject)}>
                  <span><b>{eur(i.amount_cents)}</b> <span className="muted small">{deDate(i.day)}</span></span>
                  <span className="tag">{i.kunnr ?? "unknown payer"}</span>
                  <span className="why">{i.reason}</span>
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
        <AnimatePresence mode="wait">
          <motion.div key={current.subject} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: MOTION.fast, ease: MOTION.ease }}>
            {problem && <div className="notice error" role="alert" style={{ marginBottom: 16 }}>The ERP refused: {problem}</div>}
            <ReviewDetail item={current} busy={accept.isPending || reject.isPending}
              onAccept={() => accept.mutate(current.subject)} onReject={() => reject.mutate(current.subject)} />
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
