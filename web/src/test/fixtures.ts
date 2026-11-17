export const item = {
  subject: "P00019", day: "2026-10-05", kunnr: "10004", amount_cents: 116620,
  reason: "cash discount taken after its period on 90010051", evidence: ["IBAN belongs to 10004 in the master data"],
  proposal: [{ doc: "90010051", kind: "clear", amount_cents: 116620 }],
};
export const report = {
  company: "Weber Antriebstechnik GmbH", period: { from: "2026-10-01", to: "2026-10-30", bank_days: 22 },
  planted: { payments: 566, advice_mails: 107 }, readers: {}, reuse: { collections_new_share: 0.365 },
  business_case: { clerk_hours_saved_per_month: 24.6, letters_to_paying_customers_avoided: 92 },
  gate: [{ name: "a", pass: true }],
  runs: {
    status_quo: { cash: { posted_right_share: 0.643, posted_wrong: 0, posted_wrong_eur: 0, clerk_minutes: 1212 }, collections: { letters_to_customers_who_had_paid: 93, clerk_minutes: 426 }, traces: {} },
    platform: { cash: { posted_right_share: 0.961, posted_wrong: 0, posted_wrong_eur: 0, clerk_minutes: 33 }, collections: { letters_to_customers_who_had_paid: 1, clerk_minutes: 61 }, traces: {} },
  },
};
export function mockFetch(routes: Record<string, () => Response>) {
  return (url: RequestInfo | URL) => {
    const u = String(url);
    const hit = Object.keys(routes).find((k) => u.startsWith(k));
    return Promise.resolve(hit ? routes[hit]() : new Response("{}", { status: 404 }));
  };
}
export const json = (body: unknown, status = 200) => () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
