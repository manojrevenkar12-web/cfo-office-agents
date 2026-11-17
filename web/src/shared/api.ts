export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* body was not JSON */ }
    throw new ApiError(detail);
  }
  return r.json() as Promise<T>;
}

export type Line = { doc: string | null; kind: string; amount_cents: number; reason?: string };
export type ReviewItem = { subject: string; day: string; kunnr: string | null; amount_cents: number; reason: string; proposal: Line[]; evidence: string[] };
export type Reply = { subject: string; day: string; action: string; kunnr: string | null; reason: string; proposal: Record<string, unknown>[] };
export type Span = { trace: string; span: string; parent: string | null; name: string; ms: number; attrs: Record<string, unknown> };
export type RunSummary = { cash: Record<string, number>; collections: Record<string, number>; traces: Record<string, Record<string, number>> };
export type Report = {
  company: string; period: { from: string; to: string; bank_days: number }; planted: Record<string, number>;
  readers: Record<string, number | string>; business_case: Record<string, number>; reuse: Record<string, number>;
  gate: { name: string; pass: boolean }[]; runs: Record<string, RunSummary>;
};

export const api = {
  summary: () => call<{ dev?: Report; heldout?: Report }>("/api/summary"),
  review: () => call<{ items: ReviewItem[] }>("/api/review"),
  accept: (s: string) => call<{ posted: number }>(`/api/review/${s}/accept`, { method: "POST" }),
  reject: (s: string) => call<{ rejected: string }>(`/api/review/${s}/reject`, { method: "POST" }),
  traces: (s: string) => call<{ spans: Span[] }>(`/api/traces/${s}`),
  collections: () => call<{ replies: Reply[]; drafts: { name: string; in_reply_to: string }[] }>("/api/collections"),
  draft: (n: string) => call<{ name: string; text: string }>(`/api/drafts/${n}`),
};
