import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { json, mockFetch, report } from "../../test/fixtures";
import { Overview } from "./Overview";

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

test("the month's figures come from the report", async () => {
  vi.stubGlobal("fetch", vi.fn(mockFetch({ "/api/summary": json({ dev: report }) })));
  wrap(<Overview />);
  expect((await screen.findAllByText("96.1 %")).length).toBe(2);           // the headline figure and the table
  expect(screen.getByText("24.6 h")).toBeTruthy();
  expect(screen.getByText(/Weber Antriebstechnik GmbH/)).toBeTruthy();
});

test("without a report it says how to make one", async () => {
  vi.stubGlobal("fetch", vi.fn(mockFetch({ "/api/summary": json({}) })));
  wrap(<Overview />);
  expect(await screen.findByText("No results yet")).toBeTruthy();
});
