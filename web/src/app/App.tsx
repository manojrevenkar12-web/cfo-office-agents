import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { Collections } from "../features/collections/Collections";
import { Overview } from "../features/overview/Overview";
import { ReviewQueue } from "../features/review/ReviewQueue";
import { MOTION } from "../shared/theme";

const VIEWS = { overview: ["Month", Overview], review: ["Review queue", ReviewQueue], collections: ["Collections", Collections] } as const;
type View = keyof typeof VIEWS;

export function App({ client = new QueryClient({ defaultOptions: { queries: { retry: 1 } } }) }: { client?: QueryClient }) {
  const [view, setView] = useState<View>("review");
  const Current = VIEWS[view][1];
  return (
    <QueryClientProvider client={client}>
      <main>
        <header className="top">
          <div className="brand">Debitoren <span>· agents for accounts receivable</span></div>
          <nav className="tabs" role="tablist">
            {(Object.keys(VIEWS) as View[]).map((v) => (
              <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}>{VIEWS[v][0]}</button>
            ))}
          </nav>
        </header>
        <AnimatePresence mode="wait">
          <motion.div key={view} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: MOTION.fast }}>
            <Current />
          </motion.div>
        </AnimatePresence>
      </main>
    </QueryClientProvider>
  );
}
