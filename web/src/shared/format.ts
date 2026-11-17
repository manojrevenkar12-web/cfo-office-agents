export const eur = (cents: number | null | undefined): string =>
  cents === null || cents === undefined ? "–" :
  (cents / 100).toLocaleString("de-DE", { style: "currency", currency: "EUR" });
export const pct = (x: number | null | undefined, d = 0): string => (x === null || x === undefined ? "–" : `${(100 * x).toFixed(d)} %`);
export const deDate = (iso: string): string => iso.split("-").reverse().join(".");
export const KIND: Record<string, string> = { clear: "clear", skonto: "cash discount (Skonto)", on_account: "unapplied cash" };
export const RUN: Record<string, string> = {
  status_quo: "ERP standard matching and dunning run",
  model_decides: "A model decides and posts",
  platform: "Platform agents: the model reads, code decides",
};
