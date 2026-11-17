import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { item, json, mockFetch } from "../../test/fixtures";
import { ReviewQueue } from "./ReviewQueue";

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

test("shows the reason, the evidence and the proposal, and posting it empties the queue", async () => {
  let open = [item];
  vi.stubGlobal("fetch", vi.fn(mockFetch({
    "/api/review/P00019/accept": () => { open = []; return json({ posted: 1 })(); },
    "/api/review": () => json({ items: open })(),
    "/api/traces": json({ spans: [] }),
  })));
  wrap(<ReviewQueue />);
  expect(await screen.findByText(/1 payments need a person/)).toBeTruthy();
  expect(screen.getAllByText(/cash discount taken after its period/).length).toBeGreaterThan(0);
  expect(screen.getByText("IBAN belongs to 10004 in the master data")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Post proposal" }));
  expect(await screen.findByText("Nothing to review")).toBeTruthy();
});

test("an error offers a retry that loads the queue", async () => {
  let fail = true;
  vi.stubGlobal("fetch", vi.fn(mockFetch({ "/api/review": () => (fail ? json({ detail: "down" }, 500)() : json({ items: [] })()) })));
  wrap(<ReviewQueue />);
  expect((await screen.findByRole("alert")).textContent).toContain("down");
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.getByText("Nothing to review")).toBeTruthy());
});

test("an ERP refusal is shown and the item stays", async () => {
  vi.stubGlobal("fetch", vi.fn(mockFetch({
    "/api/review/P00019/accept": json({ detail: "item 90010051 has 0 cents open" }, 409),
    "/api/review": json({ items: [item] }),
    "/api/traces": json({ spans: [] }),
  })));
  wrap(<ReviewQueue />);
  fireEvent.click(await screen.findByRole("button", { name: "Post proposal" }));
  expect(await screen.findByText(/The ERP refused: item 90010051 has 0 cents open/)).toBeTruthy();
});
