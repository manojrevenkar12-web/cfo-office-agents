import { motion } from "framer-motion";
import { MOTION } from "./theme";

export function Loading({ rows = 6, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label}>
      <p className="muted small">{label}</p>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}

export function Failed({ what, error, retry }: { what: string; error: unknown; retry: () => void }) {
  return (
    <motion.div className="notice error" role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: MOTION.base }}>
      <h3>{what} could not be loaded</h3>
      <p>{error instanceof Error ? error.message : "The service did not answer."} Check that the API runs on port 8080.</p>
      <button className="btn quiet" onClick={retry}>Try again</button>
    </motion.div>
  );
}

export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="notice">
      <h3>{title}</h3>
      <p className="muted">{children}</p>
    </div>
  );
}
